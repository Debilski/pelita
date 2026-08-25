import os
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from . import api, create_db_engine
from .db import session_context_yield as session_context


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = os.environ.get('DATABASE')
    create_db_engine(db_url, engine_echo=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)


    origins = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root():
        return {"status": "ok"}

    @app.get("/teams")
    def teams(session: Session = Depends(session_context)):
        return api.get_teams(session)


    @app.get("/team_stats")
    def team_stats(session: Session = Depends(session_context)):
        teams = api.get_teams(session)

        result = []
        for team in teams:
            win, loss, draw = api.get_result_count(session, team.slug)
            fatalerror_count = api.get_errorcount(session, team.slug)
            score = 0 if (win+loss+draw) == 0 else (win-loss) / (win+loss+draw)
            result.append({
                "id": team.id,
                "score": score,
                "wins": win,
                "draws": draw,
                "losses": loss,
                "slug": team.slug,
                "display_name": team.display_name,
                "mu": team.mu,
                "sigma": team.sigma,
                "num_timeouts": 0, # TODO !FIXME REMOVE
                "num_fatals": fatalerror_count
                })

        # result.sort(reverse=True)
        return result


    @app.get("/team_matches/{slug}")
    def team_matches(slug: str, session: Session = Depends(session_context)):
        result = api.get_wins_losses(session, slug)
        print(result)
        return result


    @app.get("/team_opponent/matches/{slug}/{opponent}")
    def team_opponent_matches(slug: str, opponent: str, limit: int = 30, session: Session = Depends(session_context)):
        result = api.get_team_opponent_matches(session, slug, opponent, limit=limit)
        # print(result)
        return result

    @app.get("/game_replay/{game_uuid}")
    def game_replay(game_uuid: str, session: Session = Depends(session_context)):
        result = api.get_game_replay(session, uuid.UUID(game_uuid))

        restored = []
        last_object = {}
        for object in result:
            if 'num_timeouts' in object:
                object['num_errors'] = object['num_timeouts']
            last_object.update(object)
            restored.append(dict(last_object))

        # print(restored[0])
        # print(restored[-1])
        return restored

    return app


app = create_app()
