from typing import Sequence

from openskill.models import PlackettLuce
from sqlalchemy.orm import aliased
from sqlmodel import Session, case, func, select

from .db import engine
from .models import Color, Game, GameOutput, GameParticipant, Outcome, Team

stats_model = PlackettLuce()


def get_team(slug) -> Team:
    with Session(engine) as session:
        stmt = select(Team).where(Team.slug == slug).limit(1)
        player = session.exec(stmt)
        return player.one()


def get_teams() -> Sequence[Team]:
    """Get players from the database.

    Returns
    -------
    players : list of strings
        the player names from the database.

    """
    with Session(engine) as session:
        stmt = select(Team)
        players = session.exec(stmt)
        return players.all()


def get_team_hash(slug):
    """Get the hash stored in the database for the player.

    Raises
    ------
    ValueError : if the player does not exist in the database

    """
    with Session(engine) as session:
        stmt = select(Team).where(Team.slug == slug).limit(1)
        team = session.exec(stmt)
        p1 = team.first()
        if p1:
            return p1.hash


def add_team(name, h):
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
    with Session(engine) as session:
        session.add(team)
        session.commit()


def add_display_name(slug, display_name):
    """Adds or updates team name to database

    Parameters
    ----------
    name : str
    team_name : str

    """
    with Session(engine) as session:
        stmt = select(Team).where(Team.slug == slug).limit(1)
        player = session.exec(stmt)
        player.one().display_name = display_name
        session.commit()


def remove_team(slug):
    """Remove a player from the database.

    Removes all games where the player ``pname`` participated.

    Parameters
    ----------
    pname : str
        the player name of the player to be removed

    """

    with Session(engine) as session:
        stmt = select(Team).where(Team.slug == slug)
        teams = session.exec(stmt)
        for team in teams:
            session.delete(team)
        session.commit()


def add_gameresult(team1_slug, team2_slug, result, final_state, std, p1_out, p2_out):
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

    stdout, stderr = std
    p1_stdout, p1_stderr = p1_out
    p2_stdout, p2_stderr = p2_out

    if not final_state:
        return

    # final_state_str = json.dumps(final_state)

    player1_had_fatal_error = len(final_state["fatal_errors"][0]) != 0
    player2_had_fatal_error = len(final_state["fatal_errors"][1]) != 0

    outcome = result_to_outcome(result)

    with Session(engine) as session:
        team1 = get_team(team1_slug)
        team2 = get_team(team2_slug)

        team1_oldmu = team1.mu
        team1_oldsigma = team1.sigma

        team2_oldmu = team2.mu
        team2_oldsigma = team2.sigma

        r1 = stats_model.rating(mu=team1.mu, sigma=team1.sigma)
        r2 = stats_model.rating(mu=team2.mu, sigma=team2.sigma)

        match result:
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

        team1.mu = new_r1[0].mu
        team1.sigma = new_r1[0].sigma

        team2.mu = new_r2[0].mu
        team2.sigma = new_r2[0].sigma


        game = Game(
            final_state=final_state,
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
                ),
            ],
            game_output=GameOutput(
                stdout=stdout, stderr=stderr,
                player1_stdout=p1_stdout, player1_stderr=p1_stderr,
                player2_stdout=p2_stdout, player2_stderr=p2_stderr
            )
        )

        session.add(game)

        session.commit()


def get_result_count(slug):
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
    with Session(engine) as session:
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


def get_game_counts():
    """Get number of games per player.

    Returns
    -------
    relevant_results : dict[name, int]

    """
    with Session(engine) as session:
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


def get_errorcount(slug):
    """Get errorcount of player1

    Parameters
    ----------
    p1_name : str
        the  name of player 1

    Returns
    -------
    fatalerror_count : errorcount
    """

    with Session(engine) as session:
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


def get_wins_losses(slug=None):
    """Get all wins and losses combined in a table of
    team | opponent | wins | losses | draws
    """

    team = aliased(GameParticipant)
    opp = aliased(GameParticipant)

    team_player = aliased(Team)
    opp_player = aliased(Team)

    with Session(engine) as session:
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
