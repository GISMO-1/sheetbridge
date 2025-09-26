from time import time
from typing import Any, Optional

from sqlalchemy import Column, JSON, Integer
from sqlmodel import SQLModel, Field, Session, create_engine, delete, select

from .config import settings

engine = create_engine(f"sqlite:///{settings.CACHE_DB_PATH}", echo=False)

class Row(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    data: dict[str, Any] = Field(sa_column=Column(JSON))


class Idempotency(SQLModel, table=True):
    key: str = Field(primary_key=True)
    created_at: int = Field(sa_column=Column(Integer, nullable=False))
    response: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

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


def save_idempotency(key: str, response: dict[str, Any]) -> None:
    with Session(engine) as session:
        session.merge(
            Idempotency(key=key, created_at=int(time()), response=response)
        )
        session.commit()


def get_idempotency(key: str, ttl_seconds: int) -> Optional[dict[str, Any]]:
    now = int(time())
    with Session(engine) as session:
        row = session.get(Idempotency, key)
        if not row:
            return None
        if now - row.created_at > ttl_seconds:
            return None
        return row.response


def purge_idempotency_older_than(ttl_seconds: int) -> int:
    cutoff = int(time()) - ttl_seconds
    with Session(engine) as session:
        statement = delete(Idempotency).where(Idempotency.created_at < cutoff)
        result = session.exec(statement)
        session.commit()
        return result.rowcount or 0
