
import enum
import itertools
import math
import queue
from collections import defaultdict, namedtuple
from io import StringIO


def sort_ranks(teams, bonusmatch=False):
    """ Re-orders a ranked list of teams such that
    the best and worst team are next to each other,
    the second best and second best are next to each other, etc.

    If bonusmatch is True, then the worst team will be left
    out until the final match

    Parameters
    ----------
    teams : ranked list of teams

    Raises
    ------
    TypeError
        if new_data is not a list
    ValueError
        if new_data has inappropriate length

    """
    if len(teams) < 2:
        return teams

    if bonusmatch:
        # pop last item from teams list
        bonus_team = [teams.pop()]
    else:
        bonus_team = []

    # if the number of teams is not even, we need to leave out another team
    l = len(teams)
    if l % 2 != 0:
        # pop last item from teams list
        remainder_team = [teams.pop()]
    else:
        remainder_team = []

    # top half
    good_teams = teams[:l//2]
    # bottom half
    bad_teams = reversed(teams[l//2:2*(l//2)])

    pairs = [team for pair in zip(good_teams, bad_teams)
                  for team in pair]
    return pairs + remainder_team + bonus_team

def identity(x):
    return x

class MatrixElem:
    def size(self, trafo=identity):
        return len(self.to_s(trafo=trafo))

    def box(self, team, *, prefix=None, postfix=None, size=None, padLeft="", padRight="", fillElem="─", highlighted=False):
        if prefix is None:
            prefix = ""
        if postfix is None:
            postfix = ""

        if size is None:
            size = 0
        else:
            size = size - len(prefix) - len(postfix)

        BOLD = '\033[1m'
        END = '\033[0m'

        padded = "{padLeft}{team}{padRight}".format(team=team, padLeft=padLeft, padRight=padRight)
        return "{prefix}{BOLD}{team:{fillElem}<{size}}{END}{postfix}".format(team=padded, prefix=prefix, postfix=postfix,
                                                                             size=size, fillElem=fillElem,
                                                                             BOLD=BOLD if highlighted else "",
                                                                             END=END if highlighted else "")




class Box(MatrixElem):
    def __init__(self, item):
        self.item = item

    def to_s(self, size=None, trafo=identity, highlighted=False):
        if isinstance(self.item, Team):
            return self.box(trafo(self.name), size=size, prefix="", padLeft=" ", padRight=" ", highlighted=highlighted)
        if isinstance(self.item, Bye):
            prefix = "──"
            # return show_team("…", prefix=prefix, padLeft=" ", padRight=" ", size=size)
            return self.box("", size=size)
        if isinstance(self.item, Team):
            prefix = "├─"
            name = trafo(self.winner) if (self.winner is not None) else "???"
            return self.box(name, prefix=prefix, padLeft=" ", padRight=" ", size=size, highlighted=highlighted)

class FinalMatch(namedtuple("FinalMatch", ["t1", "t2"]), MatrixElem):
    def __init__(self, *args, **kwargs):
        self.winner = None
    def to_s(self, size=None, trafo=identity, highlighted=False):
        prefix = "├──┨"
        postfix = "┃"
        fillElem = " "
        name = trafo(self.winner) if (self.winner is not None) else "???"
        return self.box(name, prefix=prefix, postfix=postfix, padLeft=" ", padRight=" ", fillElem=fillElem, size=size, highlighted=highlighted)

class Element(namedtuple("Element", ["char"]), MatrixElem):
    def to_s(self, size=None, trafo=identity, highlighted=False):
        return self.box(self.char, size=size, fillElem=" ", highlighted=highlighted)

class Empty(namedtuple("Empty", []), MatrixElem):
    def to_s(self, size=None, trafo=identity, highlighted=False):
        return self.box(" ", size=size, fillElem=" ")

class BorderTop(namedtuple("BorderTop", ["team", "tight"]), MatrixElem):
    def to_s(self, size=None, trafo=identity, highlighted=False):
        prefix = "│  " if not self.tight else "┐  "
        padRight = ""
        padLeft = "┏"
        postfix = "┓"
        fillElem = "━"
        return self.box("", prefix=prefix, postfix=postfix, padLeft=padLeft, padRight=padRight, fillElem=fillElem, size=size)

class BorderBottom(namedtuple("BorderBottom", ["team", "tight"]), MatrixElem):
    def to_s(self, size=None, trafo=identity, highlighted=False):
        prefix = "│  " if not self.tight else "┘  "
        padRight = ""
        padLeft = "┗"
        postfix = "┛"
        fillElem = "━"
        return self.box("", prefix=prefix, postfix=postfix, padLeft=padLeft, padRight=padRight, fillElem=fillElem, size=size)

class MatrixElem:
    def min_size(self):
        return len(self.text) + 2

class TeamElem(MatrixElem):
    def __init__(self, text, idx):
        if text is None:
            test = "???"
        self.text = text
        self.idx = idx

    def to_string(self, len=None):
        if len is None:
            len = self.min_size()
        connector = "┐ " if self.idx % 2 == 0 else "┘ "
        return f"{'': <{len}}{self.text}{connector}"


class MatchElem(MatrixElem):
    pass

class FinalElem(MatrixElem):
    def __init__(self, text):
        if text is None:
            test = "???"
        self.text = text


class EmptyElem(MatrixElem):
    def __init__(self):
        self.text = None

    def min_size(self):
        return 0

    def __str__(self) -> str:
        return ""

    def __repr__(self) -> str:
        return ""

def arrange_teams(matches):
    teams_in_round = {}
    for match in matches:
        if not match.round in teams_in_round:
            teams_in_round[match.round] = []
        if not len(match.opponents) == 2:
            raise RuntimeError(f"Match {match} must have two opponents")

        for idx, opponent in enumerate(match.opponents):
            name = opponent.name if opponent is not None else None
            teams_in_round[match.round].append(TeamElem(name, idx))

    # add final
    if match.winner is None:
        teams_in_round[match.round + 1] = [FinalElem(None)]
    else:
        teams_in_round[match.round + 1] = [FinalElem(match.opponents[match.winner].name)]

    return teams_in_round


def knockout_matrix(matches):
    """
    For now teams is a list (cols) of list (rows) of teams
    """
    teams_in_round = arrange_teams(matches)
    print(teams_in_round)

    n_teams = len(teams_in_round[0])
    n_rounds = len(teams_in_round)

    height = n_teams * 2 - 1
    width = n_rounds

    padding = 2

    matrix = [["" for _w in range(width)] for _h in range(height)]

    last_match = None

    for round in range(n_rounds):
        col = round
        left_col = round - 1

        max_name_length = max(
            len(matrix[row_idx][round])
            for row_idx in range(height)
            ) + 4

        offset = 2 ** round - 1 # offset from the top of the table
        spacing = 2 ** (round + 1) # space between entries

        # position the teams
        for t_idx, team in enumerate(teams_in_round[round]):
            idx = t_idx * spacing + offset

            if not col == n_rounds - 1:

                matrix[idx][col] = team.to_string(max_name_length)
                if t_idx % 2 == 0:
                    # place the connector halfway between this and the next index
                    next_idx  = (t_idx + 1) * spacing + offset
                    half_idx = (next_idx - next_idx) // 2
                    for row in range(idx + 1, next_idx):
                        if row == half_idx:
                            matrix[row][col] = f"{'': <{max_name_length}}├─"
                        else:
                            matrix[row][col] =  f"{'': <{max_name_length}}│ "

    print(matrix)
        #    print("M:", match)

            # if isinstance(match, Match):
            #     # find row idx of the match partners
            #     for row_idx, row in enumerate(matrix):
            #         if row[left_col] == match.t1:
            #             start_row = row_idx
            #         if row[left_col] == match.t2:
            #             end_row = row_idx
            #     middle_row = math.floor(start_row + (end_row - start_row) / 2)

            #     # draw next match
            #     for row in range(start_row, end_row):
            #         matrix[row][col] = Element('│')
            #     matrix[start_row][col] = Element('┐')
            #     matrix[end_row][col] = Element('┘')
            #     matrix[middle_row][col] = Box(match)
            #     last_match = (middle_row, col)

            # if isinstance(match, Bye):
            #     for row_idx, row in enumerate(matrix):
            #         if row[left_col] == match.team:
            #             break
            #     matrix[row_idx][col] = Box(match)

    return matrix, last_match

def print_knockout(tree, name_trafo=identity, highlight=None):
    if highlight is None:
        highlight = []

    matrix, final_match = knockout_matrix(tree)

    with StringIO() as output:
        for row in matrix:
            print("".join(row), file=output)
        return output.getvalue()

def print_knockout2(tree):
    from . import knockout_mode
    return knockout_mode.print_knockout(tree)


def makepairs(matches):

    from .tournament_state import Team, Bye, Match

    if len(matches) == 0:
        raise ValueError("Cannot prepare matches (no teams given).")
    while not len(matches) == 1:
        m = []
        pairs = itertools.zip_longest(matches[::2], matches[1::2])
        for p1, p2 in pairs:
            if p2 is not None:
                m.append(Match(p1, p2)) #  winner=None))
            else:
                m.append(Bye(p1))
        matches = m
    return matches[0]

def prepare_knockout_matches(teams):
    """ Takes a list of teams and returns the matches for the knock out stage"""
    if not len(teams) in (2, 4, 8, 16):
        raise ValueError("Only knock-out matches with 2, 4, 8 or 16 participants are supported.")

    from .tournament_state import Team, Bye, Match
    # the seed order for a tournament with 16 participants
    # if we have fewer participants (but still a power of 2),
    # we can just skip the higher numbers
    seed = [0, 15, 7, 8, 3, 12, 4, 11, 1, 14, 6, 9, 2, 13, 5, 10]

    seeded_teams = [teams[idx] for idx in seed if idx < len(teams)]

    last_round = list(seeded_teams)
    while True:
        matches = []

        for idx, (t0, t1) in enumerate(zip(last_round[0::2], last_round[1::2])):
            matches.append(Match(idx, "knockout", 1, [t0, t1]))


    return matches


def prepare_matches(teams, bonusmatch=False):

    from .tournament_state import Team, Bye, Match

    """ Takes a ranked list of teams, matches them according to sort_ranks
    and returns the Match tree.
    """

    if not teams:
        raise ValueError("No teams given to sort.")

    teams_sorted = sort_ranks(teams, bonusmatch=bonusmatch)

    # If there is a bonus match, we must ensure that it will be played
    # at the very last
    if bonusmatch:
        bonus_team = teams_sorted.pop()
        if not teams_sorted:
            return Team(bonus_team)

    # pair up the games and return the tree starting from the winning team
    match_tree = makepairs([Team(t) for t in teams_sorted])

    if bonusmatch:
        # now add enough Byes to the bonus_team
        # so that we still have a balanced tree
        # when we add the bonus_team as a final match
        team = Team(bonus_team)
        for _depth in range(tree_depth(match_tree) - 1):
            team = Bye(team)

        match_tree = Match(match_tree, team)

    # ensure we have a balanced tree
    assert is_balanced(match_tree)

    return match_tree

def is_balanced(tree):
    if isinstance(tree, Match):
        return is_balanced(tree.t1) and is_balanced(tree.t2) and tree_depth(tree.t1) == tree_depth(tree.t2)
    if isinstance(tree, Bye):
        return True
    if isinstance(tree, Team):
        return True

def tree_depth(tree):
    if isinstance(tree, Match):
        return 1 + max(tree_depth(tree.t1), tree_depth(tree.t2))
    if isinstance(tree, Bye):
        return 1 + tree_depth(tree.team)
    if isinstance(tree, Team):
        return 1

def tree_enumerate(tree):
    enumerated = defaultdict(list)

    nodes = queue.Queue()
    nodes.put((tree, 0))
    while not nodes.empty():
        node, generation = nodes.get()
        if isinstance(node, Match):
            nodes.put((node.t1, generation + 1))
            nodes.put((node.t2, generation + 1))
        if isinstance(node, Bye):
            nodes.put((node.team, generation + 1))
        if isinstance(node, Team):
            pass
        enumerated[generation].append(node)

    generations = []
    for idx in sorted(enumerated.keys()):
        generations.append(enumerated[idx])
    generations.reverse()
    return generations
