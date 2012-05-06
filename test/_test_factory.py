# -*- coding: utf-8 -*-

""" Framework to simplify test development for pelita players.

This framework allows you to easily define different tests for the behaviour of
your bots. It comes with the tools to create tests for the movement of your
bots. You can test two bots simultaneously and can specify the movements of
your enemies. You can use the framework for other types of tests as well. Just
write a create_* function and pass it as second parameter to generate_from_list.

Example
-------
>>> from _test_factory import TestMovementSettings, GeneratedTests
>>> from _test_factory import generate_from_list
>>> from pelita.datamodel import north, south, west, east, stop
>>> eat = TestMovementSettings(
...    "eat",
...    '''######
...       #0  .#
...       #    #
...       #.  1#
...       ######
...       #2  3#
...       ######''',
...    {0: (1,1), 3: (4,1)},
...    [south, north]
... )

>>> team_eat = TestMovementSettings(
...    name   = "team eat",
...    layout =
...    '''######
...       #0  .#
...       #    #
...       #2  .#
...       ######
...       #. 13#
...       ######''',
...    expect = ({0: (1,1), 3: (4,1)},
...              {0: (1,3), 2: (3,3)})
... )

>>> enemy_food = TestAttributeSettings(
...     "enemy food",
...     '''######
...        #0  .#
...        #.  1#
...        ######''',
...     "enemy_food",
...     [(4,1)]
... )

>>> tests = [eat, team_eat]
>>> generate_from_list(tests)
>>> generate_from_list([enemy_food],create_attribute_test)
>>> import unittest
>>> from pelita.player import BFSPlayer
>>> GeneratedTests.player = BFSPlayer
>>> #when using this in a file simply run unittest.main()
>>> suite = unittest.TestLoader().loadTestsFromTestCase(GeneratedTests)
>>> unittest.TextTestRunner(verbosity=2).run(suite)
<unittest.runner.TextTestResult run=3 errors=0 failures=0>

"""

import unittest
from pelita.game_master import GameMaster
from pelita.player import TestPlayer, StoppingPlayer, SimpleTeam
from pelita.datamodel import stop
from pelita.viewer import AbstractViewer

class LogViewer(AbstractViewer):
    """ The log viewer stores all information about bot position.
    """
    def __init__(self, log_to):
        self.log_to = log_to

    def observe(self, round_, turn, universe, events):
        self.log_to[(round_, turn)] = universe.bots[turn]

class GameState(object):
    def __init__(self):
        self.game_master = None
        self.movements = []
        self.log = {}

class TestMovement(unittest.TestCase):
    def setUp(self):

        self.set_up_player()

    def set_up_player(self):
        """ Override this method with setup code
        """
        pass

    def assert_movement(self, *asserted_movements):
        if not hasattr(self, "silent"):
            self.silent = False

        if not hasattr(self, "use_bots"):
            self.use_bots = 1

        if not hasattr(self, "game_state"):
            self.game_state = GameState()

        if not self.game_state.game_master:
            self.game_state.game_master = GameMaster(self.layout, 4, 200, noise=False, silent=True)

            if not self.silent:
                print " "

            team = [self.player_class()]
            if self.use_bots == 2:
                team.append(self.player_class())
            else:
                team.append(StoppingPlayer())

            enemies = [TestPlayer(list(reversed(self.enemy_moves[0]))),
                       TestPlayer(list(reversed(self.enemy_moves[1])))]

            if not self.second_team:
                self.game_state.game_master.register_team(SimpleTeam(team[0], team[1]))
                self.game_state.game_master.register_team(SimpleTeam(enemies[0], enemies[1]))
            else:
                self.game_state.game_master.register_team(SimpleTeam(enemies[0], enemies[1]))
                self.game_state.game_master.register_team(SimpleTeam(team[0], team[1]))

            self.game_state.game_master.register_viewer(LogViewer(self.game_state.log))

            self.game_state.game_master.set_initial()
            self.game_state.game_master.play()

            for i in range(0, max(test_steps)+1):
                for enemy in enemies:
                    if len(enemy.moves) == 0:
                        enemy.moves.append(stop)
                game.play_round(i)
                for bot in range(0, settings.use_bots):

                    target_pos = ""
                    if settings.expect[bot].has_key(i):
                        target_pos = "should be "+str(settings.expect[bot][i])
                        self.assertEqual(settings.expect[bot][i],
                            team[bot].current_pos)
                    if not self.silent:
                        print " ", i, ": ", team[bot].current_pos, target_pos

