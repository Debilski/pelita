#!/usr/bin/env python
# -*- coding:utf-8 -*-
from __future__ import print_function
import random
from subprocess import Popen
import sys
import time
import cStringIO

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
            self.speak(string)
            time.sleep(wait)

    def speak(self, test):
        pass

class FliteSpeaker(SpeakerModule):
    def __init__(self, flite):
        self.flite = flite

    def speak(self, text):
        Popen([self.flite, "-t", text])

class OSXSpeaker(SpeakerModule):
    def speak(self, text):
        Popen(["/usr/bin/say", text])

print = OSXSpeaker().print

print("abc def ghi")
sys.exit(0)

# Global random seed. Keep it fixed or it may be impossible
# to replicate a tournament.
# Individual matches will get a random seed derived from this.
random.seed(42)

def get_team_name(pelitagame, factory):
    cmd = [pelitagame, "--check-team", factory]
    pass

if __name__ == '__main__':
    # Command line argument parsing.
    # Oh, why must argparse be soo verbose :(
    parser = argparse.ArgumentParser(description='Run a tournament',
                                 add_help=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    parser._positionals = parser.add_argument_group('Arguments')
    parser.add_argument('pelitagame', help='The pelitagame script')
    parser._optionals = parser.add_argument_group('Options')
    parser.add_argument('--help', '-h', help='show this help message and exit',
                        action='store_const', const=True)
    parser.add_argument('--speak', '-s', help='speak loudly every messsage on stdout',
                        action='store_const', const=True)
    parser.add_argument('--rounds', '-r', help='maximum number of rounds to play per match',
                        type=int, default=300)
    parser.add_argument('--viewer', '-v', help='the pelita viewer to use',
                        default='tk')
    parser.add_argument('--teams', help='load teams from TEAMFILE',
                    metavar="TEAMFILE.json", default="teams.json")
    parser.epilog = """
TEAMFILE.json must be of the form:
    { "group0": ["Name0", "Name1", "Name2"],
      "group1": ["Name0", "Name1", "Name2"],
      "group2": ["Name0", "Name1", "Name2"],
      "group3": ["Name0", "Name1", "Name2"],
      "group4": ["Name0", "Name1", "Name2"]
    }
"""
    args = parser.parse_args()
    if args.help:
        parser.print_help()
        sys.exit(0)
