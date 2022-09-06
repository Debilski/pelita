
from dataclasses import dataclass, asdict
from datetime import datetime
import enum
import math
from pathlib import Path


#https://github.com/Drarig29/brackets-manager.js/blob/011480645a7877c0e8d741582db8ffb44e6cbafc/src/types.ts
#https://drarig29.github.io/brackets-docs/faq/#why-do-i-need-a-tournamentid
#https://help.toornament.com/starter/core-concepts-glossary#bracket

from . import POINTS_DRAW, roundrobin
from . import knockout_mode, knockout_mode_new

from uuid import uuid4

class MatchGameResult(enum.Enum):
    BLUE = 0
    RED = 1
    DRAW = 2

# stages
ROUND_ROBIN = "round-robin"
KNOCKOUT = "knockout"
LAST_CHANCE_FINAL = "last-chance-final"

POINTS_WIN = 2
POINTS_DRAW = 1

@dataclass
class Team:
    name: str
    id: int
    matches_played: int = 0

# https://github.com/Drarig29/brackets-manager.js

import typing

#@dataclass
#class MatchGameResult:
#    """All the tournament-relevant data"""
##    score: typing.Tuple[int, int]
#    time: typing.Tuple[float, float]

@dataclass
class MatchGame:
    """ A match may consist of multiple match games (as a tie-breaker). """
    match_game_id: int # uuid
    parent_id: int
    date: datetime
    stored_at: Path
    winner: MatchGameResult
    final_state: dict
    opponents: list[Team] # listed again as the order may be different

@dataclass
class Match:
    match_id: int
    stage: str # "round-robin" or "knockout" or "last-chance-finale"
    round: int
    opponents: list[Team]
    winner: MatchGameResult|None = None
    is_final: bool = False # FIXME: relevant?

@dataclass
class RoundRobinState:
    matches_played: int
    matches_total: int
    ranking: list[(Team, dict)]


class MatchPlan:
    pass


class TournamentStage:
    def __init__(self, teams) -> None:
        self.teams: list[Team] = teams
        self.matches: list[Match] = []
        self.match_games: list[MatchGame] = []

        self.draw_allowed = False
        self.num_replays = 3

    def get_match_games_for_match(self, match: Match):
        games = [game for game in self.match_games if game.parent_id == match.match_id]
        return games

    def has_next(self) -> bool:
        for match in self.matches:
            if match.winner is None:
                return True
        return False

    def play_next(self, play_fn):
        match = self.get_next()
        winner, state = play_fn(match)

        from rich import print
        if winner is not MatchGameResult.DRAW:
            print(f"Winner: [b]{match.opponents[winner.value]}[/b].")
        else:
            print(f"[b]DRAW![/b]")

        print(match, winner, state)
        self._add_match_game(match, winner, state)

        #
        ##
        for t in match.opponents:
            t.matches_played += 1
        # TODO

    def _add_match_game(self, match: Match, winner, state):
        match_games = self.get_match_games_for_match(match)

        if self.draw_allowed:
            assert len(match_games) == 0

            match_game = MatchGame(
                len(self.match_games),
                parent_id=match.match_id,
                date=0,
                stored_at="",
                winner=winner,
                final_state=state,
                opponents=match.opponents) # TODO: order could be different

            self.match_games.append(match_game)
            match.winner = winner

        else:
            assert len(match_games) < self.num_replays
            print(len(match_games))

            match_game = MatchGame(
                len(self.match_games),
                parent_id=match.match_id,
                date=0,
                stored_at="",
                winner=winner,
                final_state=state,
                opponents=match.opponents) # TODO: order could be different

            if winner in (MatchGameResult.BLUE, MatchGameResult.RED):
                match.winner = winner
                print("Storing result for match", winner, match, match_game)

        #elif match.

        # self.update_parent_match
        # self.update_ranking
        # self.update_dependent_matches
        pass

    def _update_parent_match(self):
        pass

    def _update_ranking(self):
        pass

    def _update_dependent_matches(self):
        pass

    @property
    def current_stage(self):
        return self._current_stage

    @property
    def current_ranking(self):
        return self.ranking(self.current_stage)


class RoundRobinStage(TournamentStage):
    def __init__(self, teams) -> None:
        super().__init__(teams)

        rr = roundrobin.create_matchplan(teams)
        matches = [
            Match(match_id=idx, stage=ROUND_ROBIN, opponents=[t1, t2], round=0)
            for idx, (t1, t2) in enumerate(rr)
        ]
        self.matches = matches

        self._current_stage = ROUND_ROBIN
        self.draw_allowed = True

    def get_next(self) -> Match:
        for match in self.matches:
            if match.winner is None:
                return match

    def ranking(self, stage):
        return self.rr_ranking

    @property
    def rr_ranking(self) -> RoundRobinState:

        rr_total = [match for match in self.matches if match.stage == ROUND_ROBIN]
        rr_played = [match for match in rr_total if match.winner is not None]

        team_data = {
            team.id: {
                "points": 0,
                "matches": 0,
                "wins": 0,
                "losses": 0,
                "draws": 0,
            } for team in self.teams
        }

        for match in rr_played:
            for team in match.opponents:
                team_data[team.id]['matches'] += 1

            winner = match.winner
            if winner is not MatchGameResult.DRAW and winner is not None:
                winner_uuid = match.opponents[winner.value].id
                loser_uuid = match.opponents[1 - winner.value].id

                team_data[winner_uuid]['wins'] += 1
                team_data[loser_uuid]['losses'] += 1

            else:
                for team in match.opponents:
                    team_data[team.id]['draws'] += 1

        for team in self.teams:
            team_data[team.id]['points'] = (
                team_data[team.id]['wins'] * POINTS_WIN +
                team_data[team.id]['losses'] * 0 +
                team_data[team.id]['draws'] * POINTS_DRAW
            )

        class TeamInRR:
            def __lt__(self, other):
                # The ranking goes:
                # - Match points
                # - Direct comparison
                # - Number of wins
                # - Points scored
                # - Least number of timeouts
                # - Least time taken

                return self.points < other.points # + count losses ...

        team_points = [(team, team_data[team.id]) for team in self.teams]
        ranking = sorted(team_points, key=lambda elem: elem[1]["points"], reverse=True)

        return RoundRobinState(len(rr_played), len(rr_total), ranking)

class LastChanceFinalStage(TournamentStage):
    def __init__(self, teams) -> None:
        self.matches: list[Match] = []
        self.match_games: dict[str, MatchGame] = {}
        self.teams: list[Team] = teams

def prepare_knockout_matches(teams):
    """ Takes a list of teams and returns the matches for the knock out stage"""
    if not len(teams) in (2, 4, 8, 16):
        raise ValueError("Only knock-out matches with 2, 4, 8 or 16 participants are supported.")

    all_matches = []

    # rounds until we have a winner
    num_rounds = int(math.log2(len(teams)))
    num_matches = len(teams) // 2
    for round in range(num_rounds):
        for match_id in range(num_matches):
            match = Match(match_id=match_id, stage="knockout", round=round, opponents=[None, None])
            all_matches.append(match)

        num_matches = num_matches // 2

    # the seed order for a tournament with 16 participants
    # if we have fewer participants (but still a power of 2),
    # we can just skip the higher numbers
    seed = [0, 15, 7, 8, 3, 12, 4, 11, 1, 14, 6, 9, 2, 13, 5, 10]

    seeded_teams = [teams[idx] for idx in seed if idx < len(teams)]

    # Fill the opponents for the first matches
    for idx, team in enumerate(seeded_teams):
        all_matches[idx // 2].opponents[idx % 2] = team

    return all_matches


class KnockoutStage(TournamentStage):
    def __init__(self, teams) -> None:
        super().__init__(teams)
        self.matches = prepare_knockout_matches(teams)

        self._current_stage = KNOCKOUT

    def get_next(self) -> Match:
        for idx, match in enumerate(self.matches):
            if match.winner is None:
                # check if our opponents are ready
                if match.opponents[0] is None:
                    parent = self.find_parent_match(match, 0)
                    match.opponents[0] = parent.opponents[parent.winner.value]

                if match.opponents[1] is None:
                    parent = self.find_parent_match(match, 1)
                    match.opponents[1] = parent.opponents[parent.winner.value]
                return match

    def find_parent_match(self, match, idx):
        # finds the parent match
        round = match.round
        match_id = match.match_id
        for m in self.matches:
            if m.round == round - 1 and m.match_id == match_id * 2 + idx:
                return m
        raise RuntimeError(f"Match {match} has no parent in {self} for idx {idx}.")

    def ranking(self, _):
        return self.matches

# Configure size of knockout

"""
        1 ┐
          ├─ ??? ┐
        4 ┘      │
                 ├─ ??? ┐
        2 ┐      │      │  ┏━━━━━┓
          ├─ ??? ┘      ├──┨ ??? ┃
        3 ┘             │  ┗━━━━━┛
                        │
        5 ──────────────┘

        1 ──────────────┐
                        |
        2 ┐             |
          ├─ ??? ┐      |
        4 ┘      │      |
                 ├─ ???
        2 ┐      │      │
          ├─ ??? ┘      ├─ ??? ┐
        3 ┘             │      │  ┏━━━━━┓
                        │      ├──┨ ??? ┃
        5 ──────────────┘      │  ┗━━━━━┛
                               │
        6 ─────────────────────┘

"""


def mock_play(match: Match) -> tuple[MatchGameResult, dict]:
    import random
    t0 = match.opponents[0]
    t1 = match.opponents[1]

    from rich import print
    print(f"[b]Playing [i]mock game[/i][/b] {match}: {t0} against {t1}.")

    res = random.choice(
        [
            MatchGameResult.BLUE, MatchGameResult.BLUE, MatchGameResult.RED, MatchGameResult.DRAW, MatchGameResult.DRAW, MatchGameResult.DRAW, MatchGameResult.DRAW, MatchGameResult.DRAW
    ]

    )
    return res, {}


def pp_round1_results(rr_state: RoundRobinState):
    from rich import print as print
    from rich.console import Console
    console = Console()

    BOLD = '\033[1m'
    END = '\033[0m'

    """Pretty print the current result of the matches."""
    n_played = rr_state.matches_played
    es = "es" if n_played != 1 else ""
    n_togo = rr_state.matches_total - rr_state.matches_played

    print()
    print('Ranking after {n_played} match{es} ({n_togo} to go):'.format(n_played=n_played, es=es, n_togo=n_togo))
    for team, points in rr_state.ranking:
        #if team_id in highlight:
        #    print("  {BOLD}{:>25}{END} {}".format(config.team_name(team_id), p, BOLD=BOLD, END=END))
        #else:
            console.print("  [b]{:>25}[/b] {}".format(f"{team.name} ({team.matches_played})", str(points)), highlight=False)
    print()

team_ids = [Team(name=f'#{idx}...', id=idx) for idx in range(5)]
matchplan = RoundRobinStage(team_ids)

while match := matchplan.has_next():
    matchplan.play_next(mock_play)
    pp_round1_results(matchplan.current_ranking)

print("---")

top_4 = [team for team, _ in matchplan.current_ranking.ranking[:4]]
matchplan = KnockoutStage(top_4)

print(top_4, matchplan)


def build_match_tree(matches, winners_in_bold=True):
    teams = []
    tree_pos = {}

    for match in matches:
        if match.round == 0:
            for team in match.opponents:
                teams.append(team.name)

        if match.winner is not None:
            winner = match.opponents[match.winner.value].name, int(match.winner.value)
        else:
            winner = "???", None
        tree_pos[(match.round, match.match_id)] = winner

    # TODO: Underline winning teams
    # TODO: Print current match in bold or italic

    def gen_empty_tree(n_rounds, path=None, bold=False):
        if path == None:
            path = [0]
        idx = 0
        for i, n in enumerate(reversed(path)):
            idx += n * 2 ** i

        @dataclass
        class StyledEntry:
            text: str
            style: str
            def __str__(self) -> str:
                return f"[{self.style}]{self.text}[/{self.style}]"
            def __len__(self) -> int:
                return len(self.text)

        # return a binary tree for num_teams at the base
        if n_rounds == 0:
            # fill teams:
            team = teams[idx]
            if bold:
                team = f"{team}"
            return team # (team, n_rounds, idx)

        match_winner, winner_idx = tree_pos[n_rounds - 1, idx]
        if bold:
            match_winner = f"{match_winner}"
        return [
            gen_empty_tree(n_rounds - 1, path + [0], winner_idx == 0),
            match_winner, # (match_winner, n_rounds, idx),
            gen_empty_tree(n_rounds - 1, path + [1], winner_idx == 1)
        ]

    depth = int(math.log2(len(teams)))
    empty_tree = gen_empty_tree(depth)
    #print(empty_tree)
    return empty_tree

def add_last_chance_final(match_tree, loser_team):
    return [match_tree, '???', loser_team]

print(build_match_tree(matchplan.current_ranking))

while match := matchplan.has_next():
    matchplan.play_next(mock_play)

    #print(matchplan.current_ranking)
    #for round in matchplan.current_ranking:
        #for
    from rich.console import Console
    console = Console()

    from .bracket import print_tree
    print(print_tree(add_last_chance_final(build_match_tree(matchplan.current_ranking), 'loser_team')))


#    print(knockout_mode_new.print_knockout(matchplan.current_ranking))




raise 0



ko = prepare_knockout_matches(team_ids[:4])
for kom in ko:
    print(yaml.dump(asdict(kom), sort_keys=False))
#print(ko)

# TODO: Excluding the bonus match, which team should get byes? The best ones or the worst ones?


#teams = "teams"
#state = "state"

#{teams: [{ {teams: [{  }, {   }], state: None} }, {  {teams: [{  }, {   }], state: None} }], state: None}

#class TournamentState:
#    pass


#class Tournament:
#    state: pass
