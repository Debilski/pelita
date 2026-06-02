#!/usr/bin/env python3

# Copyright (c) 2013, Bastian Venthur <venthur@debian.org>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the
#    distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Continuous Integration Engine.

Currently this module is only usable as a script, later it shall be
extended to be used as a library for a web service providing a
continuous integration service.

In its current form it is still very usable to test a couple of agents
automatically against each other and compare the results. For best
results modify the ``agents`` section in the ``ci.cfg`` configuration
file and run this file. Leave it running for a while until the positions
stabilized.

"""

import argparse
import asyncio
import configparser
import itertools
import logging
import operator
import shlex
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory

from rich.console import Console
from rich.progress import (Progress, SpinnerColumn, TextColumn,
                           TimeElapsedColumn)
from rich.table import Table

from pelita.network import RemotePlayerFailure, RemotePlayerSendError, RemotePlayerRecvTimeout
from pelita.scripts.script_utils import start_logging
from pelita.tournament import call_pelita, check_team

from . import api, db
from .db import session_context
from .models import FinishedGame

_logger = logging.getLogger(__name__)

# the path of the configuration file
CFG_FILE = './ci.cfg'

EXIT = threading.Event()

def signal_handler(_signal, _frame):
    _logger.warning('Program terminated by kill or ctrl-c')
    EXIT.set()
    sys.exit()

signal.signal(signal.SIGINT, signal_handler)

async def hash_team(team_spec, semaphore):
    external_call = [sys.executable,
                    '-m',
                    'pelita.scripts.pelita_player',
                    'hash-team',
                    team_spec]
    async with semaphore:
        _logger.debug("Executing: %r", shlex.join(external_call))
        proc = await asyncio.create_subprocess_exec(*external_call,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        _logger.info(f"Hash for {team_spec}: {stdout}")

    return stdout.decode().strip().split("\n")[-1].strip()


def run_game(team_specs, config) -> FinishedGame:
    """Run a single game.

    This method runs a single game and returns the result.

    Parameters
    ----------
    p1, p2 : int
        the indices of the players

    """
    with TemporaryDirectory() as tmpdir:
        replay_file = Path(tmpdir) / "replay"

        final_state, stdout, stderr = call_pelita(team_specs,
                                                            rounds=config['rounds'],
                                                            size=config['size'],
                                                            viewer=config['viewer'],
                                                            seed=config['seed'],
                                                            store_output=tmpdir,
                                                            write_replay=str(replay_file),
                                                            timeout=10,
                                                            initial_timeout=120,
                                                            exit_flag=EXIT
                                                            )

        if not final_state:
            result = None

        if final_state['game_phase'] != 'FINISHED':
            _logger.info("Game finished in phase %s", final_state['game_phase'])
            result = -2
        else:
            if final_state['whowins'] == 2:
                result = -1
            else:
                result = final_state['whowins']

        try:
            del final_state['walls']
            del final_state['food']
        except IndexError:
            pass

        _logger.info('Final state: %r', final_state)
        _logger.debug('Stdout: %r', stdout)
        if stderr:
            _logger.warning('Stderr: %r', stderr)

        finished_game = FinishedGame()
        finished_game.result = result
        finished_game.final_state = final_state

        finished_game.replay = (Path(tmpdir) / 'replay').read_text()

        finished_game.game_stdout = stdout
        finished_game.game_stderr = stderr

        finished_game.p1_stdout = (Path(tmpdir) / 'blue.out').read_text()
        finished_game.p1_stderr = (Path(tmpdir) / 'blue.err').read_text()

        finished_game.p2_stdout = (Path(tmpdir) / 'red.out').read_text()
        finished_game.p2_stderr = (Path(tmpdir) / 'red.err').read_text()

        return finished_game

class Config:
    rounds: int | None
    size: str | None
    viewer: str
    seed: str | None
    db_url: str
    players: dict[str, str]


def read_config(cfgfile, database=None) -> Config:
    cfg = Config()

    cfg_path = Path(cfgfile)

    cfg.players = {}
    config = configparser.ConfigParser()
    config.read(cfgfile)
    for name, path in  config.items('agents'):
        cfg.players[name]= str(cfg_path.parent / path)


    cfg.rounds = config['general'].getint('rounds', None)
    cfg.size = config['general'].get('size', None)
    cfg.viewer = config['general'].get('viewer', 'null')
    cfg.seed = config['general'].get('seed', None)

    db_file = database or config.get('general', 'db_file')

    if ":" not in db_file:
        cfg.db_url = f"sqlite:///{db_file}"
    else:
        cfg.db_url = db_file

    return cfg

def create_db_engine(db_url, engine_echo):
    db.engine = db.create_engine(db_url, echo=engine_echo)
    db.create_db_and_tables()


def load_players(cfg_players, concurrency=1):
    with session_context() as session:
        # remove players from db which are not in the config anymore
        for path in api.get_teams(session):
            if path.slug not in cfg_players:
                _logger.debug('Removing %s from database, because it is not among the current players.' % (path.slug))
                api.remove_team(session, path.slug) # ???

        semaphore = asyncio.Semaphore(concurrency)

        async def do_hash():
            tasks = [asyncio.create_task(hash_team(path, semaphore)) for path in cfg_players.values()]
            hashes = await asyncio.gather(*tasks)
            return {slug: hash for (slug, hash) in zip(cfg_players, hashes)}

        hash_cache = asyncio.run(do_hash())

        # add new players into db
        for slug, path in cfg_players.items():
            if slug not in [p.slug for p in api.get_teams(session)]:
                _logger.debug('Adding %s to database.' % slug)
                api.add_team(session, slug, hash_cache[slug])

        # reset players where the directory hash changed
        for slug, path in cfg_players.items():
            new_hash = hash_cache[slug]
            if new_hash != api.get_team_hash(session, slug):
                _logger.debug('Resetting %s because its module hash changed.' % slug)
                api.remove_team(session, slug)
                api.add_team(session, slug, new_hash)

        def check_team_name(args):
            slug, path = args
            try:
                _logger.debug('Querying team name for %s.' % slug)
                team_name = check_team(path, timeout=6*concurrency)
                return team_name
            except (RemotePlayerSendError, RemotePlayerRecvTimeout, RemotePlayerFailure) as e:
                _logger.debug(f'Could not import {slug} at path {path}: {e}')
                # TODO: Forward error
                return None

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            display_names = executor.map(check_team_name, cfg_players.items())

        ok_players = dict(cfg_players)

        for slug, display_name in zip(cfg_players, display_names):
            if display_name is None:
                del ok_players[slug]
            else:
                api.add_display_name(session, slug, display_name)

    # Returning the players that could be loaded
    # In the future this could maybe flag in the database
    return ok_players


def start_engine(config, cfg_players, n, concurrency):
    """Start the Engine.

    This method will start and run n matches, testing each agent
    randomly against another one. The result is printed after each
    game.

    Currently the only way to stop the engine is via CTRL-C.

    Examples
    --------
    >>> ci = CI_Engine()
    >>> ci.start()

    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn()
    ) as progress:

        lock = threading.Lock()

        def worker(count, p1_slug, p2_slug) -> tuple[int, tuple[str, str], FinishedGame]:
            with lock:
                progress_task = progress.add_task(f"Playing #{count}: {p1_slug} against {p2_slug}.")

            game_config = {
                'rounds': config.rounds,
                'size': config.size,
                'viewer': config.viewer,
                'seed': None, # TODO
            }

            team_specs = [cfg_players[p1_slug], cfg_players[p2_slug]]
            finished_game = run_game(team_specs, game_config)

            with lock:
                progress.update(progress_task, completed=True, visible=False)

            return count, (p1_slug, p2_slug), finished_game

        def producer():
            rng = Random()

            with session_context() as session:
                game_counts = {slug: num for slug, num in api.get_game_counts(session).items() if slug in cfg_players}

            for count in range(n):
                # TODO: Delete failed?
                # for slug, path in players.items():
                #     if "error" in path and slug in game_counts:
                #         del game_counts[slug]

                # choose the player with the least number of played games,
                # match with another random player
                # shuffle the sides and let them play

                players_sorted = sorted(list(game_counts.items()), key=operator.itemgetter(1))

                a = players_sorted[0][0]
                b = rng.choice(players_sorted[1:])[0]

                players = [a, b]
                rng.shuffle(players)

                _logger.debug(f"Adding match {count} ({players[0]} vs {players[1]}) to worker queue")
                task = (count, players[0], players[1])

                yield task

                game_counts[a] += 1
                game_counts[b] += 1


        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            if sys.version_info < (3, 14):
                _logger.warning(f"Generating all {n} match partners. Use Python 3.14+ to do this lazily.")
                buffersize = {}
            else:
                buffersize = {'buffersize': concurrency * 10}

            for result in executor.map(lambda args: worker(*args), producer(), **buffersize):
                count, player_slugs, finished_game = result

                p1_slug, p2_slug = player_slugs

                final_state = finished_game.final_state

                if final_state and final_state["game_phase"] == "FINISHED":
                    match final_state["whowins"]:
                        case 0:
                            progress.console.print(f"Storing #{count}: [u]{p1_slug}[/u] against {p2_slug}.")
                        case 1:
                            progress.console.print(f"Storing #{count}: {p1_slug} against [u]{p2_slug}[/u].")
                        case _:
                            progress.console.print(f"Storing #{count}: {p1_slug} against {p2_slug}.")
                    with session_context() as session:
                        api.add_gameresult(session, p1_slug, p2_slug, finished_game)
                else:
                    progress.console.print(f"Not storing #{count}: {p1_slug} against {p2_slug}.")


def pretty_print_results(full=False, team_slug=None, highlight=None, html_export=None):
    """Pretty print the current results.

    """
    if highlight is None:
        highlight = []

    console = Console(record=True)

    table = Table(title="Bot ranking")

    table.add_column("Name")
    table.add_column("# Matches")
    table.add_column("# Wins")
    table.add_column("# Draws")
    table.add_column("# Losses")
    table.add_column("Score")
    table.add_column("μ")
    table.add_column("σ")
    table.add_column("# Fatal Errors")

    with session_context() as session:
        teams = api.get_teams(session)

        result = []
        for team in teams:
            win, loss, draw = api.get_result_count(session, team.slug)
            fatalerror_count = api.get_errorcount(session, team.slug)
            score = 0 if (win+loss+draw) == 0 else (win-loss) / (win+loss+draw)
            result.append([score, win, draw, loss, team.slug, team.display_name, team.mu, team.sigma, fatalerror_count])

    result.sort(reverse=True)
    for [score, win, draw, loss, name, team_name, mu, sigma, fatalerror_count] in result:
        style = "bold" if name in highlight else None
        display_name = f"{name} ({team_name})" if team_name else f"{name}"
        table.add_row(
            display_name,
            f"{win+draw+loss}",
            f"{win}",
            f"{draw}",
            f"{loss}",
            f"{score:6.3f}",
            f"{mu:6.2f}",
            f"{sigma:6.2f}",
            f"{fatalerror_count}",
            style=style,
        )

    console.print(table)

    if full:
        # Some guesswork in here
        MAX_COLUMNS = (console.width - 40) // 12
        if MAX_COLUMNS < 4:
            # Let’s be honest: You should enlarge your terminal window even before that
            MAX_COLUMNS = 4

        with session_context() as session:
            res = list(api.get_wins_losses(session))
        rows = { k: list(v) for k, v in itertools.groupby(res, key=lambda x:x['team']) }

        num_rows_per_player = (len(teams) // MAX_COLUMNS) + 1
        row_style = [*([""] * num_rows_per_player), *(["dim"] * num_rows_per_player)]

        table = Table(row_styles=row_style, title="Cross results")
        table.add_column("")
        table.add_column("Name")
        table.add_column("Score", justify="right")
        table.add_column("W/D/L")

        column_players = [[] for _idx in range(min(MAX_COLUMNS, len(teams)))]
        # if we have more teams than allowed columns, we must wrap around
        for idx, _p in enumerate(teams):
            column_players[idx % MAX_COLUMNS].append(idx)

        for midx in column_players:
            table.add_column('\n'.join(map(str, midx)))


        def batched(iterable, n):
            # Backport from Python 3.12
            # batched('ABCDEFG', 3) → ABC DEF G
            if n < 1:
                raise ValueError('n must be at least one')
            iterator = iter(iterable)
            while batch := tuple(itertools.islice(iterator, n)):
                yield batch

        with session_context() as session:
            teams = api.get_teams(session)

            for idx, team in enumerate(teams):
                win, loss, draw = api.get_result_count(session, team.slug)
                score = 0 if (win+loss+draw) == 0 else (win-loss) / (win+loss+draw)
                wdl = f"{win:3d},{draw:3d},{loss:3d}"

                try:
                    row = rows[team.slug]
                except KeyError:
                    continue
                vals = { e['opponent']: (e['wins'], e['losses'], e['draws']) for e in row }

                cross_results = []
                for idx2, opponent in enumerate(teams):
                    win, loss, draw = vals.get(opponent.slug, (0, 0, 0))
                    if idx == idx2:
                        cross_results.append("  - - - ")
                    else:
                        cross_results.append(f"{win:2d},{draw:2d},{loss:2d}")

                for c, r in enumerate(batched(cross_results, MAX_COLUMNS)):
                    if c == 0:
                        table.add_row(f"{idx}", team.slug, f"{score:.2f}", wdl, *r)
                    else:
                        table.add_row("", "", "", "", *r)

        console.print(table)

    elif team_slug:
        MAX_COLUMNS = (console.width - 40) // 12
        if MAX_COLUMNS < 4:
            # Let’s be honest: You should enlarge your terminal window even before that
            MAX_COLUMNS = 4

        with session_context() as session:
            res = api.get_wins_losses(session, team_slug)
            rows = {k: list(v) for k, v in itertools.groupby(res, key=lambda x:x['team'])}

            row_style = ["", "dim"]

            table = Table(row_styles=row_style, title=f"Match results for team {team}")
            table.add_column("Name")
            table.add_column("# Matches")
            table.add_column("# Wins")
            table.add_column("# Draws")
            table.add_column("# Losses")

            teams = api.get_teams(session)
            for idx, team in enumerate(teams):
                try:
                    row = rows[team.slug]
                except KeyError:
                    continue

                for r in row: # there should only be one row
                    win, loss, draw = r['wins'], r['losses'], r['draws']

                    display_name = f"{team.slug} ({team.display_name})" if team.display_name else f"{team.slug}"

                    table.add_row(
                        display_name,
                        f"{win+draw+loss}",
                        f"{win}",
                        f"{draw}",
                        f"{loss}",
                    )

        console.print(table)

    if html_export:
        console.save_html(html_export)

def run(args):
    cfg = read_config(args.config, args.database)

    create_db_engine(cfg.db_url, engine_echo=args.db_echo)
    if not args.no_hash:
        ok_players = load_players(cfg.players, concurrency=args.thread_count)
    else:
        ok_players = cfg.players
    start_engine(cfg, ok_players, args.n, args.thread_count)

def print_scores(args):
    cfg = read_config(args.config, args.database)
    create_db_engine(cfg.db_url, engine_echo=args.db_echo)
    pretty_print_results(full=args.full, team_slug=args.team, html_export=args.html_export)

def hash_teams(args):
    cfg = read_config(args.config, args.database)
    create_db_engine(cfg.db_url, engine_echo=args.db_echo)
    load_players(cfg.players, concurrency=args.thread_count)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', help="Print debugging log information to LOGFILE (default 'stderr').",
                        metavar='LOGFILE', const='-', nargs='?')
    parser.add_argument('--db-echo', help="Print db log information to the command line.",
                        action='store_true', default=False)
    parser.add_argument('--config', help="Print debugging log information to LOGFILE (default 'stderr').",
                        metavar='FILE', default=CFG_FILE)
    parser.add_argument('--database', help="Database location",
                        metavar='FILE', default=None)

    subparsers = parser.add_subparsers(required=True)

    parser_run = subparsers.add_parser('run')
    parser_run.add_argument('-n', help='run N times', type=int, default=1000)
    parser_run.add_argument('--thread-count', '-t', help='run in parallel', type=int, default=1)
    parser_run.add_argument('--no-hash', help='Do not hash the players prior to running', action='store_true', default=False)
    parser_run.set_defaults(func=run)

    parser_print_scores = subparsers.add_parser('print-scores')
    parser_print_scores.add_argument('--html-export', help='output as HTML', default=False)
    full_or_team = parser_print_scores.add_mutually_exclusive_group()
    full_or_team.add_argument('--full', help='show full pair statistics', action='store_true', default=False)
    full_or_team.add_argument('--team', help='show statistics for team', type=str, default=None)
    parser_print_scores.set_defaults(func=print_scores)

    parser_hash = subparsers.add_parser('hash-teams')
    parser_hash.set_defaults(func=hash_teams)
    parser_hash.add_argument('--thread-count', '-t', help='run in parallel', type=int, default=1)

    args = parser.parse_args()

    if args.log is not None:
        start_logging(args.log, __name__)
        start_logging(args.log, 'pelita')

    args.func(args)

if __name__ == '__main__':
    main()
