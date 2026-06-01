from sqlalchemy import Engine
from sqlmodel import SQLModel, create_engine, Session
from . import models

engine: Engine | None = None

def session_context():
    return Session(engine)

def create_db_and_tables():
    if not engine:
        raise RuntimeError("Must create global engine first.")
    SQLModel.metadata.create_all(engine)
