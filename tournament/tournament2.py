#!/usr/bin/env python
# -*- coding:utf-8 -*-
from __future__ import print_function
import random
from subprocess import Popen, PIPE
import sys
import time
import cStringIO
import ConfigParser

import logging

# silence stupid warnings from logging module
logging.root.manager.emittedNoHandlerWarning = 1

_logger = logging.getLogger("pelita.tournament")

CFG_FILE = "./tournament.cfg"

# Drop this as soon as we drop support for python 2.6
try:
    import argparse
except ImportError:
    from pelita.compat import argparse

LOGFILE = open("loggg", 'w')
SPEAK = True

def _print(*args, **kwargs):
    __builtins__.print(*args, **kwargs)
    kwargs['file'] = LOGFILE
    __builtins__.print(*args, **kwargs)

class SpeakerModule(object):
    def print(self, *args, **kwargs):
        """Speak while you print. To disable set speak=False.
        Set wait=X to wait X seconds after speaking."""
        if len(args) == 0:
            _print()
            return
        want_speak = kwargs.pop('speak', SPEAK)
        if not want_speak:
            _print(*args, **kwargs)
        else:
            stream = cStringIO.StringIO()
            wait = kwargs.pop('wait', 0.5)
            __builtins__.print(*args, file=stream, **kwargs)
            string = stream.getvalue()
            _print(string, end='')
            sys.stdout.flush()
            self._speak(string)
            time.sleep(wait)

    def _speak(self, test):
        pass

class FliteSpeaker(SpeakerModule):
    def __init__(self, flite):
        self.flite = flite

    def _speak(self, text):
        Popen([self.flite, "-t", text])

class OSXSpeaker(SpeakerModule):
    def _speak(self, text):
        Popen(["/usr/bin/say", text])

class NoSpeaker(SpeakerModule):
    def _speak(self, text):
        pass

# Global random seed. Keep it fixed or it may be impossible
# to replicate a tournament.
# Individual matches will get a random seed derived from this.
random.seed(42)

class PelitaRunner(object):
    def __init__(self, pelitagame, dry_run=False):
        self.pelitagame = pelitagame
        self.dry_run = dry_run

    def get_team_name(self, team_spec):
        cmd = [self.pelitagame, "--check-team", team_spec]
        _logger.debug("cmd %r", cmd)
        stdout, stderr = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()
        try:
            return stdout.splitlines()[-1]
        except IndexError:
            _logger.warn(stderr)

    def run_match(self, spec1, spec2):
        cmd = [self.pelitagame, spec1, spec2]


class RoundRobin(object):
    def __init__(self, teams):
        self.teams = teams
        self.results = []
        self.to_play = [(t1, t2) if random.randint(0, 1) else (t2, t1)
                                 for idx1, t1 in enumerate(self.teams)
                                 for idx2, t2 in enumerate(self.teams)
                                 if idx1 < idx2]

        random.shuffle(self.to_play)

    def play(self):
        while self.to_play:
            match = self.to_play.pop()
            team1, team2 = match
            result = run_match(team1, team2)
            self.add_result(match, result)

    def add_result(self, match):
        self.results += [(match, result)]

    def ranking(self):
        print(self.results)

class MatchTree(object):
    def __init__(self, tree1, tree2):
        self.tree1 = tree1
        self.tree2 = tree2



class KnockOutRound(object):
    def __init__(self, ranked_teams, number_teams=4, last_chance_match=True):
        if len(ranked_teams) <= number_teams + bool(last_chance_match):
            raise ValueError("Not enough teams")

        self.all_teams = ranked_teams
        self.number_teams = number_teams
        self.last_chance_match = last_chance_match

        if self.last_chance_match:
            self.last_chance_team = self.all_teams[-1]
        self.ko_teams = self.all_teams[:self.number_teams]

        if self.last_chance_match:
            do_match(old_winner, self.last_chance_team)

def start_logging(filename):
    hdlr = logging.FileHandler(filename, mode='w')
    logger = logging.getLogger('pelita')
    FORMAT = \
    '[%(relativeCreated)06d %(name)s:%(levelname).1s][%(funcName)s] %(message)s'
    formatter = logging.Formatter(FORMAT)
    hdlr.setFormatter(formatter)
    logger.addHandler(hdlr)
    logger.setLevel(logging.DEBUG)

if __name__ == '__main__':
    # Command line argument parsing.
    parser = argparse.ArgumentParser(description='Run a tournament',
                                 add_help=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    parser._positionals = parser.add_argument_group('Arguments')
    parser.add_argument('pelitagame', help='The pelitagame script')
    parser._optionals = parser.add_argument_group('Options')
    parser.add_argument('--help', '-h', help='show this help message and exit',
                        action='store_const', const=True)
    parser.add_argument('--verbose', '-v', help='print before executing commands',
                        action='store_const', const=True)
    parser.add_argument('--dry-run', help='do not actually run the matches',
                        action='store_const', const=True)
    parser.add_argument('--cfg', help='path to the configuration file',
                        default=CFG_FILE)
    parser.add_argument('--speak', '-s', help='speak loudly every messsage on stdout',
                        action='store_const', const=True)
    parser.add_argument('--rounds', '-r', help='maximum number of rounds to play per match',
                        type=int, default=300)
    parser.add_argument('--viewer', help='the pelita viewer to use',
                        default='tk')
    parser.add_argument('--teams', help='load teams from TEAMFILE',
                    metavar="TEAMFILE.json", default="teams.json")
    args = parser.parse_args()
    if args.help:
        parser.print_help()
        sys.exit(0)

    if args.verbose:
        start_logging("/dev/stdout")

    if args.speak:
        print = OSXSpeaker().print
    else:
        print = NoSpeaker().print

    config = ConfigParser.RawConfigParser()
    config.read(args.cfg)

    teams = config.items("teams")
    teams = dict(teams).values()

    runner = PelitaRunner(args.pelitagame, args.dry_run)
    spec_names = {}
    for team in teams:
        spec_names[team] = runner.get_team_name(team)

    for (t1, t2) in RoundRobin(spec_names.keys()):
        print(t1)

    for team in spec_names.values():
        print(runner.get_team_name(team))

