from sqlmodel import SQLModel, create_engine
from . import models

engine = None

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
