from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import SQLModel, Field, create_engine, Session, select

from .config import settings

engine = create_engine(f"sqlite:///{settings.CACHE_DB_PATH}", echo=False)

class Row(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    data: dict[str, Any] = Field(sa_column=Column(JSON))

def init_db():
    SQLModel.metadata.create_all(engine)

def upsert_rows(rows: list[dict]):
    with Session(engine) as s:
        for r in rows:
            obj = Row(data=r)
            s.add(obj)
        s.commit()

def list_rows(limit: int = 100, offset: int = 0):
    with Session(engine) as s:
        stmt = select(Row).offset(offset).limit(limit)
        return [r.data for r in s.exec(stmt)]
