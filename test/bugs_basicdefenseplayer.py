from _test_factory import TestMovement
from pelita.datamodel import north, south, west, east, stop
from pelita.player import BasicDefensePlayer


class TestBasicDefensePlayer(TestMovement):
    def setUp(self):
        self.layout = (
        """ ########
            #2    1#
            #.  ##.#
            #.  0#.#
            #   ##3#
            ######## """)
        self.second_team = True
        self.player_class = BasicDefensePlayer

    def test_BDPlayer(self):
        self.enemy_moves = ([west, stop, stop, stop],
                            [west, west, stop, east, east])

        self.assert_movement({0: (6,1), 5:(4,1)},
                             {0: (6,4)})

class TestBasicDefensePlayer2(TestMovement):
    def setUp(self):
        self.layout = (
        """ ########
            #0  ##1#
            #    # #
            #      #
            #.####.#
            #   2  #
            ########
            #     3#
            ######## """)
        self.second_team = True
        self.player_class = BasicDefensePlayer

    def test_BDPlayer(self):
        self.enemy_moves = ([],
                            [west, stop])
        self.assert_movement({0: (6,1), 1:(6,2), 2:(6,3), 3:(5,3)})

class TestBasicDefensePlayer3(TestMovement):
    def setUp(self):
        self.layout = (
        """ ########
            #2  ##1#
            #    # #
            #      #
            #.####.#
            #   0  #
            ########
            #     3#
            ######## """)
        self.second_team = True
        self.player_class = BasicDefensePlayer

    def test_BDPlayer(self):
        self.enemy_moves = ([west, stop],
                            [])
        self.assert_movement({0: (6,1), 1:(6,2), 2:(6,3), 3:(5,3)})

if __name__ == '__main__':
    import unittest
    unittest.main()
