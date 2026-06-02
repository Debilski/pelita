from enum import IntEnum
from typing import Optional

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import (JSON, Column, Field, Relationship, SQLModel,
                      UniqueConstraint)


JSONType = JSON().with_variant(JSONB(), "postgresql")


class Color(IntEnum):
    BLUE = 1
    RED = 2


class Outcome(IntEnum):
    LOSS = 0
    DRAW = 1
    WIN = 2


class Team(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    display_name: str | None
    hash: str

    participations: list["GameParticipant"] = Relationship(
        back_populates="team",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
        },
    )

    # OpenSkill state
    mu: float = 25.0
    sigma: float = 25.0 / 3.0


class Game(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    final_state: Optional[dict] = Field(sa_column=Column(JSONType))

    participants: list["GameParticipant"] = Relationship(
        back_populates="game",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
        },
    )

    game_output: Optional["GameOutput"] = Relationship(
        back_populates="game",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
        },
    )

    game_replay: Optional["GameReplay"] = Relationship(
        back_populates="game",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
        },
    )


class GameParticipant(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("game_id", "color"),)

    id: int | None = Field(default=None, primary_key=True)

    game_id: int = Field(foreign_key="game.id", ondelete="CASCADE")
    team_id: int = Field(foreign_key="team.id", ondelete="CASCADE")

    color: Color
    outcome: Outcome

    had_fatal_error: bool = False

    game: Game = Relationship(back_populates="participants")
    team: Team = Relationship(back_populates="participations")
    game_participant_output: Optional["GameParticipantOutput"] = Relationship(
        back_populates="game_participant",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
        },
    )

    # snapshot before game
    mu_before: float
    sigma_before: float

    # snapshot after game
    mu_after: float
    sigma_after: float

class GameOutput(SQLModel, table=True):
    game_id: int = Field(default=None, primary_key=True, foreign_key="game.id", ondelete="CASCADE")

    stdout: str
    stderr: str

    game: Game = Relationship(back_populates="game_output")


class GameReplay(SQLModel, table=True):
    game_id: int = Field(default=None, primary_key=True, foreign_key="game.id", ondelete="CASCADE")

    replay: dict = Field(sa_column=Column(JSONType))

    game: Game = Relationship(back_populates="game_replay")


class GameParticipantOutput(SQLModel, table=True):
    gameparticipant_id: int = Field(default=None, primary_key=True, foreign_key="gameparticipant.id", ondelete="CASCADE")

    stdout: str
    stderr: str

    game_participant: GameParticipant = Relationship(back_populates="game_participant_output")


class FinishedGame:
    result: int | None
    final_state: dict
    game_stdout: str
    game_stderr: str
    p1_stdout: str
    p1_stderr: str
    p2_stdout: str
    p2_stderr: str
    replay: str | None
