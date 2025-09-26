from time import time
from typing import Any, Optional

from sqlalchemy import Column, Integer, JSON, Text, cast, func
from sqlmodel import Field, Session, SQLModel, create_engine, delete, select

from .config import settings

engine = create_engine(f"sqlite:///{settings.CACHE_DB_PATH}", echo=False)

class Row(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    data: dict[str, Any] = Field(sa_column=Column(JSON))
    created_at: int = Field(
        sa_column=Column(Integer, nullable=False, default=int(time()))
    )


class Idempotency(SQLModel, table=True):
    key: str = Field(primary_key=True)
    created_at: int = Field(sa_column=Column(Integer, nullable=False))
    response: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

def init_db():
    SQLModel.metadata.create_all(engine)

    with engine.begin() as connection:
        table_name = Row.__tablename__
        pragma_rows = connection.exec_driver_sql(
            f"PRAGMA table_info('{table_name}')"
        ).all()
        has_created_at = any(column[1] == "created_at" for column in pragma_rows)

        if not has_created_at:
            connection.exec_driver_sql(
                f'ALTER TABLE "{table_name}" ADD COLUMN created_at INTEGER'
            )
            connection.exec_driver_sql(
                f'UPDATE "{table_name}" '
                "SET created_at = CAST(strftime('%s', 'now') AS INTEGER) "
                "WHERE created_at IS NULL"
            )

def insert_rows(rows: list[dict]):
    now = int(time())
    with Session(engine) as session:
        for row in rows:
            session.add(Row(data=row, created_at=now))
        session.commit()


def upsert_rows(rows: list[dict]):
    insert_rows(rows)


def list_rows(limit: int = 100, offset: int = 0):
    rows, _ = query_rows(
        q=None,
        columns=None,
        since_unix=None,
        limit=limit,
        offset=offset,
    )
    return rows


def query_rows(
    q: Optional[str],
    columns: Optional[list[str]],
    since_unix: Optional[int],
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    with Session(engine) as session:
        stmt = select(Row)
        if since_unix is not None:
            stmt = stmt.where(Row.created_at >= since_unix)
        if q:
            lowered = q.lower()
            stmt = stmt.where(
                func.lower(cast(Row.data, Text)).like(f"%{lowered}%")
            )

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = session.exec(total_stmt).one()
        total = total_result[0] if isinstance(total_result, tuple) else total_result

        paged_stmt = stmt.offset(offset).limit(limit)
        result_rows = [row.data for row in session.exec(paged_stmt)]

        if columns:
            allowed = set(columns)
            result_rows = [
                {key: value for key, value in row.items() if key in allowed}
                for row in result_rows
            ]

        return result_rows, int(total)


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
