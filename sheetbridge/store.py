from time import time
from typing import Any, Optional

from sqlalchemy import Column, Integer, JSON, String, Text, cast, func
from sqlmodel import Field, Session, SQLModel, create_engine, delete, select

from .config import settings

engine = create_engine(f"sqlite:///{settings.CACHE_DB_PATH}", echo=False)

class Row(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    key: str | None = Field(
        default=None,
        sa_column=Column(String, nullable=True, index=True),
    )
    data: dict[str, Any] = Field(sa_column=Column(JSON))
    created_at: int = Field(
        sa_column=Column(Integer, nullable=False, default=int(time()))
    )


class Idempotency(SQLModel, table=True):
    key: str = Field(primary_key=True)
    created_at: int = Field(sa_column=Column(Integer, nullable=False))
    response: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class DeadLetter(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reason: str = Field(sa_column=Column(String, nullable=False))
    data: dict[str, Any] = Field(sa_column=Column(JSON))
    created_at: int = Field(
        sa_column=Column(Integer, nullable=False, default=int(time()))
    )

def init_db():
    SQLModel.metadata.create_all(engine)

    with engine.begin() as connection:
        table_name = Row.__tablename__
        pragma_rows = connection.exec_driver_sql(
            f"PRAGMA table_info('{table_name}')"
        ).all()
        has_created_at = any(column[1] == "created_at" for column in pragma_rows)
        has_key = any(column[1] == "key" for column in pragma_rows)

        if not has_created_at:
            connection.exec_driver_sql(
                f'ALTER TABLE "{table_name}" ADD COLUMN created_at INTEGER'
            )
            connection.exec_driver_sql(
                f'UPDATE "{table_name}" '
                "SET created_at = CAST(strftime('%s', 'now') AS INTEGER) "
                "WHERE created_at IS NULL"
            )
        if not has_key:
            connection.exec_driver_sql(
                f'ALTER TABLE "{table_name}" ADD COLUMN key TEXT'
            )
        connection.exec_driver_sql(
            f'CREATE INDEX IF NOT EXISTS idx_{table_name}_key '
            f'ON "{table_name}" (key)'
        )

def insert_rows(rows: list[dict]) -> int:
    now = int(time())
    key_column = getattr(settings, "KEY_COLUMN", None)
    with Session(engine) as session:
        inserted = 0
        for row in rows:
            key_value: str | None = None
            if key_column:
                value = row.get(key_column)
                if value is not None:
                    key_value = str(value)
            session.add(Row(key=key_value, data=row, created_at=now))
            inserted += 1
        session.commit()
        return inserted


def upsert_rows(rows: list[dict]) -> int:
    return insert_rows(rows)


def upsert_by_key(rows: list[dict], key_column: str, strict: bool = True) -> int:
    now = int(time())
    with Session(engine) as session:
        touched = 0
        for row in rows:
            key_value = row.get(key_column)
            if key_value is None:
                if strict:
                    raise ValueError(f"missing key {key_column}")
                continue
            key_text = str(key_value)
            existing = session.exec(
                select(Row).where(Row.key == key_text)
            ).first()
            if existing:
                existing.data = row
                existing.created_at = now
                touched += 1
            else:
                session.add(Row(key=key_text, data=row, created_at=now))
                touched += 1
        session.commit()
        return touched


def find_duplicates(key_column: str):
    if not key_column:
        return []
    with Session(engine) as session:
        statement = (
            select(Row.key, func.count(Row.key))
            .group_by(Row.key)
            .having(func.count(Row.key) > 1)
        )
        return [
            {"key": key, "count": count}
            for key, count in session.exec(statement)
            if key is not None
        ]


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


def dlq_write(reason: str, data: dict[str, Any]) -> None:
    with Session(engine) as session:
        session.add(DeadLetter(reason=reason, data=data))
        session.commit()


def dlq_list(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    with Session(engine) as session:
        statement = (
            select(DeadLetter)
            .order_by(DeadLetter.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return [
            {
                "id": row.id,
                "reason": row.reason,
                "data": row.data,
                "created_at": row.created_at,
            }
            for row in session.exec(statement)
        ]
