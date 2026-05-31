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

from pelita.network import RemotePlayerFailure
from pelita.scripts.script_utils import start_logging
from pelita.tournament import call_pelita, check_team

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

    return stdout.decode().strip().split("\n")[-1].strip()


def run_game(team_specs, config):
    """Run a single game.

    This method runs a single game and returns the result.

    Parameters
    ----------
    p1, p2 : int
        the indices of the players

    """

    with TemporaryDirectory() as tmpdir:
        final_state, stdout, stderr = call_pelita(team_specs,
                                                            rounds=config['rounds'],
                                                            size=config['size'],
                                                            viewer=config['viewer'],
                                                            seed=config['seed'],
                                                            store_output=tmpdir,
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

        p1_stdout = (Path(tmpdir) / 'blue.out').read_text()
        p1_stderr = (Path(tmpdir) / 'blue.err').read_text()

        p2_stdout = (Path(tmpdir) / 'red.out').read_text()
        p2_stderr = (Path(tmpdir) / 'red.err').read_text()

        res = (result, final_state, [stdout, stderr], [p1_stdout, p1_stderr], [p2_stdout, p2_stderr])
        return res



class CI_Engine:
    """Continuous Integration Engine."""

    def __init__(self, cfgfile, database=None):
        self.cfg_path = Path(cfgfile)

        self.players = {}
        config = configparser.ConfigParser()
        config.read(cfgfile)
        for name, path in  config.items('agents'):
            self.players[name]= {'path': str(self.cfg_path.parent / path)}


        self.rounds = config['general'].getint('rounds', None)
        self.size = config['general'].get('size', None)
        self.viewer = config['general'].get('viewer', 'null')
        self.seed = config['general'].get('seed', None)

        self.db_file = database or config.get('general', 'db_file')

        sqlite_url = f"sqlite:///{self.db_file}"

        from . import db
        db.engine = db.create_engine(sqlite_url, echo=True)
        db.create_db_and_tables()

        from . import api
        self.dbwrapper = api

    def load_players(self, concurrency=1):
        hash_cache = {}

        # remove players from db which are not in the config anymore
        for player in self.dbwrapper.get_teams():
            if player.slug not in self.players:
                _logger.debug('Removing %s from database, because it is not among the current players.' % (player.slug))
                self.dbwrapper.remove_team(player.slug) # ???

        semaphore = asyncio.Semaphore(concurrency)

        async def do_hash():
            players = [(pname, player['path']) for pname, player in self.players.items()]
            tasks = [asyncio.create_task(hash_team(player[1], semaphore)) for player in players]
            hashes = await asyncio.gather(*tasks)
            return {player[0]: hash for (player, hash) in zip(players, hashes)}

        hash_cache = asyncio.run(do_hash())

        # add new players into db
        for pname, player in self.players.items():
            path = player['path']
            if pname not in [p.slug for p in self.dbwrapper.get_teams()]:
                _logger.debug('Adding %s to database.' % pname)
                self.dbwrapper.add_team(pname, hash_cache[pname])

        # reset players where the directory hash changed
        for pname, player in self.players.items():
            path = player['path']
            new_hash = hash_cache[pname]
            if new_hash != self.dbwrapper.get_team_hash(pname):
                _logger.debug('Resetting %s because its module hash changed.' % pname)
                self.dbwrapper.remove_team(pname)
                self.dbwrapper.add_team(pname, new_hash)

        def check_team_name(args):
            pname, path = args
            try:
                _logger.debug('Querying team name for %s.' % pname)
                team_name = check_team(path, timeout=6*concurrency)
                return { 'team_name': team_name }
            except RemotePlayerFailure as e:
                e_type, e_msg = e.args
                _logger.debug(f'Could not import {pname} at path {path} ({e_type}): {e_msg}')
                return { 'error': e.args }

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            players = [(pname, player['path']) for pname, player in self.players.items()]
            team_names = executor.map(check_team_name, players)

            for (pname, path), team_name in zip(players, team_names):
                if 'error' in team_name:
                    self.players[pname]['error'] = team_name['error']
                else:
                    self.dbwrapper.add_display_name(pname, team_name['team_name'])

        for pname in self.players:
             if 'error' in self.players[pname]:
                 print(pname, self.players[pname])
             else:
                 print(pname, self.players[pname], self.dbwrapper.get_team(pname).display_name)

    def start(self, n, concurrency):
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

            def worker(count, p1, p2):
                with lock:
                    progress_task = progress.add_task(f"Playing #{count}: {p1} against {p2}.")

                config = {
                    'rounds': self.rounds,
                    'size': self.size,
                    'viewer': self.viewer,
                    'seed': None, # TODO
                }

                team_specs = [self.players[p1]['path'], self.players[p2]['path']]
                res = run_game(team_specs, config)

                with lock:
                    progress.update(progress_task, completed=True, visible=False)

                return count, (p1, p2), res

            def producer():
                rng = Random()

                game_counts = self.dbwrapper.get_game_counts()

                for count in range(n):
                    for pname, player in self.players.items():
                        if "error" in player and pname in game_counts:
                            del game_counts[pname]

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
                    buffersize = {'buffersize': concurrency}

                for result in executor.map(lambda args: worker(*args), producer(), **buffersize):
                    count, players, res = result

                    p1_name, p2_name = players
                    winner, final_state, out, p1_out, p2_out = res

                    if final_state:
                        match final_state["whowins"]:
                            case 0:
                                progress.console.print(f"Storing #{count}: [u]{players[0]}[/u] against {players[1]}.")
                            case 1:
                                progress.console.print(f"Storing #{count}: {players[0]} against [u]{players[1]}[/u].")
                            case _:
                                progress.console.print(f"Storing #{count}: {players[0]} against {players[1]}.")
                    else:
                        progress.console.print(f"Not storing #{count}: {players[0]} against {players[1]}.")
                    self.dbwrapper.add_gameresult(p1_name, p2_name, winner, final_state, out, p1_out, p2_out)

    def get_errorcount(self, p_name):
        """Gets the error count for team idx

        Parameters
        ----------
        idx : int
            the index of the player

        Returns
        -------
        fatalerror_count : int
            the number of errors for this player

        """
        fatalerror_count = self.dbwrapper.get_errorcount(p_name)
        return fatalerror_count

    def pretty_print_results(self, full=False, team=None, highlight=None, html_export=None):
        """Pretty print the current results.

        """
        if highlight is None:
            highlight = []

        good_players = [p for p, player in self.players.items() if not player.get('error')]
        bad_players = [p for p, player in self.players.items() if player.get('error')]

        console = Console(record=True)

        table = Table(title="Bot ranking")

        table.add_column("Name")
        table.add_column("# Matches")
        table.add_column("# Wins")
        table.add_column("# Draws")
        table.add_column("# Losses")
        table.add_column("Score")
        table.add_column("ELO")
        table.add_column("# Fatal Errors")

        elo = {}
        # elo = self.gen_elo()

        result = []
        for idx, pname in enumerate(good_players):
            win, loss, draw = self.dbwrapper.get_result_count(pname)
            fatalerror_count = self.get_errorcount(pname)
            try:
                team_name = self.dbwrapper.get_team(pname).display_name
            except ValueError:
                team_name = None
            score = 0 if (win+loss+draw) == 0 else (win-loss) / (win+loss+draw)
            result.append([score, win, draw, loss, pname, team_name, fatalerror_count])

        result.sort(reverse=True)
        for [score, win, draw, loss, name, team_name, fatalerror_count] in result:
            style = "bold" if name in highlight else None
            display_name = f"{name} ({team_name})" if team_name else f"{name}"
            table.add_row(
                display_name,
                f"{win+draw+loss}",
                f"{win}",
                f"{draw}",
                f"{loss}",
                f"{score:6.3f}",
                f"{elo.get(name, 0): >4.0f}",
                f"{fatalerror_count}",
                style=style,
            )

        console.print(table)

        for p in bad_players:
            print("% 30s ***%30s***" % (p, self.players[p]['error']))


        if full:
            # Some guesswork in here
            MAX_COLUMNS = (console.width - 40) // 12
            if MAX_COLUMNS < 4:
                # Let’s be honest: You should enlarge your terminal window even before that
                MAX_COLUMNS = 4

            res = list(self.dbwrapper.get_wins_losses())
            rows = { k: list(v) for k, v in itertools.groupby(res, key=lambda x:x['team']) }

            num_rows_per_player = (len(good_players) // MAX_COLUMNS) + 1
            row_style = [*([""] * num_rows_per_player), *(["dim"] * num_rows_per_player)]

            table = Table(row_styles=row_style, title="Cross results")
            table.add_column("")
            table.add_column("Name")
            table.add_column("Score", justify="right")
            table.add_column("W/D/L")

            column_players = [[] for _idx in range(min(MAX_COLUMNS, len(good_players)))]
            # if we have more good_players than allowed columns, we must wrap around
            for idx, _p in enumerate(good_players):
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

            for idx, pname in enumerate(good_players):
                win, loss, draw = self.dbwrapper.get_result_count(pname)

                fatalerror_count = self.get_errorcount(pname)
                try:
                    team_name = self.dbwrapper.get_team(pname).display_name
                except ValueError:
                    team_name = None
                score = 0 if (win+loss+draw) == 0 else (win-loss) / (win+loss+draw)
                wdl = f"{win:3d},{draw:3d},{loss:3d}"

                try:
                    row = rows[pname]
                except KeyError:
                    continue
                vals = { e['opponent']: (e['wins'], e['losses'], e['draws']) for e in row }

                cross_results = []
                for idx2, p2name in enumerate(good_players):
                    win, loss, draw = vals.get(p2name, (0, 0, 0))
                    if idx == idx2:
                        cross_results.append("  - - - ")
                    else:
                        cross_results.append(f"{win:2d},{draw:2d},{loss:2d}")

                for c, r in enumerate(batched(cross_results, MAX_COLUMNS)):
                    if c == 0:
                        table.add_row(f"{idx}", pname, f"{score:.2f}", wdl, *r)
                    else:
                        table.add_row("", "", "", "", *r)

            console.print(table)

        elif team:
            MAX_COLUMNS = (console.width - 40) // 12
            if MAX_COLUMNS < 4:
                # Let’s be honest: You should enlarge your terminal window even before that
                MAX_COLUMNS = 4

            res = self.dbwrapper.get_wins_losses(slug=team)
            rows = {k: list(v) for k, v in itertools.groupby(res, key=lambda x:x['team'])}

            row_style = ["", "dim"]

            table = Table(row_styles=row_style, title=f"Match results for team {team}")
            table.add_column("Name")
            table.add_column("# Matches")
            table.add_column("# Wins")
            table.add_column("# Draws")
            table.add_column("# Losses")

            for idx, pname in enumerate(good_players):
                try:
                    team_name = self.dbwrapper.get_team(pname).display_name
                except ValueError:
                    team_name = None

                try:
                    row = rows[pname]
                except KeyError:
                    continue

                for r in row: # there should only be one row
                    win, loss, draw = r['wins'], r['losses'], r['draws']

                    display_name = f"{pname} ({team_name})" if team_name else f"{pname}"

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
    ci_engine = CI_Engine(args.config, args.database)
    if not args.no_hash:
        ci_engine.load_players(concurrency=args.thread_count)
    ci_engine.start(args.n, args.thread_count)

def print_scores(args):
    ci_engine = CI_Engine(args.config, args.database)
    ci_engine.pretty_print_results(full=args.full, team=args.team, html_export=args.html_export)

def hash_teams(args):
    ci_engine = CI_Engine(args.config, args.database)
    ci_engine.load_players(concurrency=args.thread_count)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', help="Print debugging log information to LOGFILE (default 'stderr').",
                        metavar='LOGFILE', const='-', nargs='?')
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
