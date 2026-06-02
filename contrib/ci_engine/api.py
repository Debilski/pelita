import json
import logging
from typing import Sequence

from openskill.models import PlackettLuce
from sqlalchemy.orm import aliased
from sqlmodel import Session, case, func, select

from .db import engine
from .models import Color, FinishedGame, Game, GameOutput, GameParticipant, GameParticipantOutput, GameReplay, Outcome, Team

stats_model = PlackettLuce()

STORE_REPLAY = True

_logger = logging.getLogger(__name__)

def get_team(session: Session, slug) -> Team:
    stmt = select(Team).where(Team.slug == slug).limit(1)
    player = session.exec(stmt)
    return player.one()


def get_teams(session: Session) -> Sequence[Team]:
    """Get players from the database.

    Returns
    -------
    players : list of strings
        the player names from the database.

    """
    stmt = select(Team)
    players = session.exec(stmt)
    return players.all()


def get_team_hash(session: Session, slug):
    """Get the hash stored in the database for the player.

    Raises
    ------
    ValueError : if the player does not exist in the database

    """
    stmt = select(Team).where(Team.slug == slug).limit(1)
    team = session.exec(stmt)
    p1 = team.first()
    if p1:
        return p1.hash


def add_team(session: Session, name, h):
    """Add player to database

    Parameters
    ----------
    name : str
    h : str
        hash of the player's directory

    Raises
    ------
    ValueError : if player already exists in database

    """
    team = Team(slug=name, display_name=None, hash=h)
    session.add(team)
    session.commit()
    session.refresh(team)
    return team


def add_display_name(session: Session, slug, display_name):
    """Adds or updates team name to database

    Parameters
    ----------
    name : str
    team_name : str

    """
    stmt = select(Team).where(Team.slug == slug).limit(1)
    result = session.exec(stmt)
    team = result.one()
    team.display_name = display_name
    session.commit()
    session.refresh(team)
    return team


def remove_team(session: Session, slug):
    """Remove a player from the database.

    Removes all games where the player ``pname`` participated.

    Parameters
    ----------
    pname : str
        the player name of the player to be removed

    """

    stmt = select(Team).where(Team.slug == slug)
    teams = session.exec(stmt)
    for team in teams:
        session.delete(team)
    session.commit()


def add_gameresult(session: Session, team1_slug, team2_slug, finished_game: FinishedGame):
    """Add a new game result to the database.

    Parameters
    ----------
    p1_name, p2_name : str
        the names of the players
    result : 0, 1 or -1
        0 if player 1 won
        1 of player 2 won
        -1 if draw
        -2 if anything other than game_phase FINISHED
    std_out, std_err : str
        STDOUT and STDERR of the game

    """

    def result_to_outcome(result):
        match result:
            case 0:
                return [Outcome.WIN, Outcome.LOSS]
            case 1:
                return [Outcome.LOSS, Outcome.WIN]
            case -1:
                return [Outcome.DRAW, Outcome.DRAW]

    if not finished_game.final_state:
        return

    # final_state_str = json.dumps(final_state)

    player1_had_fatal_error = len(finished_game.final_state["fatal_errors"][0]) != 0
    player2_had_fatal_error = len(finished_game.final_state["fatal_errors"][1]) != 0

    outcome = result_to_outcome(finished_game.result)

    team1 = get_team(session, team1_slug)
    team2 = get_team(session,team2_slug)

    team1_oldmu = team1.mu
    team1_oldsigma = team1.sigma

    team2_oldmu = team2.mu
    team2_oldsigma = team2.sigma

    r1 = stats_model.rating(mu=team1.mu, sigma=team1.sigma)
    r2 = stats_model.rating(mu=team2.mu, sigma=team2.sigma)

    match finished_game.result:
        case 0:
            new_r1, new_r2 = stats_model.rate(
                [[r1], [r2]],
                ranks=[0, 1],
            )
        case 1:
            new_r1, new_r2 = stats_model.rate(
                [[r1], [r2]],
                ranks=[1, 0],
            )
        case -1:
            new_r1, new_r2 = stats_model.rate(
                [[r1], [r2]],
                ranks=[0, 0],
            )
        case _:
            _logger.warning("Cannot store bad result.")
            return

    team1.mu = new_r1[0].mu
    team1.sigma = new_r1[0].sigma

    team2.mu = new_r2[0].mu
    team2.sigma = new_r2[0].sigma


    game = Game(
        final_state=finished_game.final_state,
        participants=[
            GameParticipant(
                team=team1,
                color=Color.BLUE,
                outcome=outcome[0],
                had_fatal_error=player1_had_fatal_error,
                mu_before=team1_oldmu,
                sigma_before=team1_oldsigma,
                mu_after=team1.mu,
                sigma_after=team2.sigma,
                game_participant_output=GameParticipantOutput(
                    stdout=finished_game.p1_stdout,
                    stderr=finished_game.p1_stderr
                )

            ),
            GameParticipant(
                team=team2,
                color=Color.RED,
                outcome=outcome[1],
                had_fatal_error=player2_had_fatal_error,
                mu_before=team2_oldmu,
                sigma_before=team2_oldsigma,
                mu_after=team2.mu,
                sigma_after=team2.sigma,
                game_participant_output=GameParticipantOutput(
                    stdout=finished_game.p2_stdout,
                    stderr=finished_game.p2_stderr
                )
            ),
        ],
        game_output=GameOutput(
            stdout=finished_game.game_stdout, stderr=finished_game.game_stderr,
        )
    )

    if finished_game.replay and STORE_REPLAY:
        # TODO: It should be configurable whether we want to store replays in the db or externally
        json_data = load_jsonls(finished_game.replay)

        game.game_replay=GameReplay(
            replay=json_data
        )

    session.add(game)
    session.commit()
    session.refresh(game)
    return game


def load_jsonls(jsonls):
    return [json.loads(line) for line in jsonls.split('\n') if line.strip()]


def get_errorcount(session: Session, slug):
    """Get errorcount of player1

    Parameters
    ----------
    p1_name : str
        the  name of player 1

    Returns
    -------
    """
    stmt = (
        select(
            Team.id,
            Team.slug,
            func.sum(
                case((GameParticipant.had_fatal_error, 1), else_=0)
            ).label("fatal_errors"),
        )
        .outerjoin(GameParticipant, GameParticipant.team_id == Team.id)
        .group_by(Team.id)
        .where((Team.slug == slug))
    )

    res = session.exec(stmt).one()
    return res.fatal_errors


def get_result_count(session: Session, slug: str):
    """Get all games involving player1 (AND player2 if specified).

    Parameters
    ----------
    p1_name : str
        the  name of player 1
    p2_name : str, optional
        the name of player 2, if not specified ``get_results`` will
        return all games involving player 1 otherwise it will return
        all games of player1 AND player2

    Returns
    -------
    relevant_results : list of gameresults

    """
    stmt = (
        select(
            Team.id,
            Team.slug,
            func.sum(
                case(
                    (GameParticipant.outcome == Outcome.WIN, 1),
                    else_=0,
                )
            ).label("wins"),
            func.sum(
                case(
                    (GameParticipant.outcome == Outcome.DRAW, 1),
                    else_=0,
                )
            ).label("draws"),
            func.sum(
                case(
                    (GameParticipant.outcome == Outcome.LOSS, 1),
                    else_=0,
                )
            ).label("losses"),
        )
        .outerjoin(
            GameParticipant,
            Team.id == GameParticipant.team_id,
        )
        .group_by(Team.id, Team.slug)
        .where(Team.slug == slug)
    )

    relevant_results = session.exec(stmt).one()
    return relevant_results.wins, relevant_results.losses, relevant_results.draws


def get_game_counts(session: Session) -> dict[str, int]:
    """Get number of games per player.

    Returns
    -------
    relevant_results : dict[name, int]
    """
    stmt = (
        select(
            Team.id,
            Team.slug,
            func.count(GameParticipant.game_id).label("num_games"),
        )
        .outerjoin(GameParticipant, GameParticipant.team_id == Team.id)
        .group_by(Team.id, Team.slug)
    )

    result = {
        player_name: num_games
        for team_id, player_name, num_games in session.exec(stmt).all()
    }
    return result


def get_wins_losses(session: Session, slug=None):
    """Get all wins and losses combined in a table of
    team | opponent | wins | losses | draws
    """

    team = aliased(GameParticipant)
    opp = aliased(GameParticipant)

    team_player = aliased(Team)
    opp_player = aliased(Team)

    stmt = (
        select(
            # team_player.display_name.label('team_name'),
            team_player.slug.label("team"),
            # opp_player.display_name.label('opp_name'),
            opp_player.slug.label("opponent"),
            func.sum(case((team.outcome == Outcome.WIN, 1), else_=0)).label("wins"),
            func.sum(case((team.outcome == Outcome.DRAW, 1), else_=0)).label(
                "draws"
            ),
            func.sum(case((team.outcome == Outcome.LOSS, 1), else_=0)).label(
                "losses"
            ),
        )
        .join(
            opp,
            (team.game_id == opp.game_id) & (team.team_id != opp.team_id),
        )
        .join(team_player, team.team_id == team_player.id)
        .join(opp_player, opp.team_id == opp_player.id)
        .group_by(
            team_player.id,
            opp_player.id,
        )
    )
    if slug:
        stmt = stmt.where(team_player.slug == slug)

    res = session.exec(stmt).mappings().all()
    return res
