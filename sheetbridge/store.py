from pathlib import Path
from time import time
from typing import Any, Optional

from sqlalchemy import Column, Integer, JSON, String, Text, cast, func
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, create_engine, delete, select

from .config import settings

engine: Engine | None = None


def _db_path() -> Path:
    path = Path(settings.CACHE_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def refresh_engine() -> None:
    global engine
    if engine is not None:
        engine.dispose()
    db_path = _db_path()
    engine = create_engine(f"sqlite:///{db_path}", echo=False)


def _get_engine() -> Engine:
    global engine
    desired = str(_db_path())
    if engine is None or engine.url.database != desired:
        refresh_engine()
    assert engine is not None
    return engine

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
    _prepare_schema()


def _prepare_schema() -> Engine:
    eng = _get_engine()

    SQLModel.metadata.create_all(eng)

    with eng.begin() as connection:
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

    return eng

def insert_rows(rows: list[dict]) -> int:
    eng = _prepare_schema()
    now = int(time())
    key_column = getattr(settings, "KEY_COLUMN", None)
    with Session(eng) as session:
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


def upsert_rows_bulk(rows: list[dict]):
    insert_rows(rows)


def upsert_by_key(rows: list[dict], key_column: str, strict: bool = True) -> int:
    eng = _prepare_schema()
    now = int(time())
    with Session(eng) as session:
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


def upsert_by_key_bulk(rows: list[dict], key_column: str, strict: bool):
    upsert_by_key(rows, key_column, strict)


def find_duplicates(key_column: str):
    if not key_column:
        return []
    eng = _prepare_schema()
    with Session(eng) as session:
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
    eng = _prepare_schema()
    with Session(eng) as session:
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
    eng = _prepare_schema()
    with Session(eng) as session:
        session.merge(
            Idempotency(key=key, created_at=int(time()), response=response)
        )
        session.commit()


def get_idempotency(key: str, ttl_seconds: int) -> Optional[dict[str, Any]]:
    eng = _prepare_schema()
    now = int(time())
    with Session(eng) as session:
        row = session.get(Idempotency, key)
        if not row:
            return None
        if now - row.created_at > ttl_seconds:
            return None
        return row.response


def purge_idempotency_older_than(ttl_seconds: int) -> int:
    eng = _prepare_schema()
    cutoff = int(time()) - ttl_seconds
    with Session(eng) as session:
        statement = delete(Idempotency).where(Idempotency.created_at < cutoff)
        result = session.exec(statement)
        session.commit()
        return result.rowcount or 0


def dlq_write(reason: str, data: dict[str, Any]) -> None:
    eng = _prepare_schema()
    with Session(eng) as session:
        session.add(DeadLetter(reason=reason, data=data))
        session.commit()


def dlq_list(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    eng = _prepare_schema()
    with Session(eng) as session:
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


def dlq_fetch(limit: int = 50):
    eng = _prepare_schema()
    with Session(eng) as session:
        stmt = select(DeadLetter).order_by(DeadLetter.id).limit(limit)
        return list(session.exec(stmt))


def dlq_delete(ids: list[int]):
    if not ids:
        return
    eng = _prepare_schema()
    with Session(eng) as session:
        for identifier in ids:
            session.exec(delete(DeadLetter).where(DeadLetter.id == identifier))
        session.commit()
