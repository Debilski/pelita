from enum import IntEnum
from typing import Optional

from sqlmodel import (JSON, Column, Field, Relationship, SQLModel,
                      UniqueConstraint)


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


class Game(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    final_state: Optional[dict] = Field(sa_column=Column(JSON))

    participants: list["GameParticipant"] = Relationship(
        back_populates="game",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
        },
    )


class GameParticipant(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("game_id", "color"),)
    game_id: int = Field(foreign_key="game.id", primary_key=True, ondelete="CASCADE")
    team_id: int = Field(foreign_key="team.id", primary_key=True, ondelete="CASCADE")

    color: Color
    outcome: Outcome

    had_fatal_error: bool = False

    game: Game = Relationship(back_populates="participants")
    team: Team = Relationship(back_populates="participations")


class GameOutput(SQLModel, table=True):
    game_id: int = Field(default=None, primary_key=True, foreign_key="game.id", ondelete="CASCADE")

    stdout: str
    stderr: str
    player1_stdout: str
    player1_stderr: str
    player2_stdout: str
    player2_stderr: str
