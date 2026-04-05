from __future__ import annotations

from pathlib import Path

from peewee import SqliteDatabase

database = SqliteDatabase(
    None,
    pragmas={
        "journal_mode": "wal",
        "foreign_keys": 1,
        "cache_size": -1024 * 64,
        "synchronous": 1,
    },
)


def init_database(db_path: Path) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    current_path = getattr(database, "database", None)
    target_path = str(db_path)

    if current_path != target_path:
        if not database.is_closed():
            database.close()
        database.init(target_path)

    database.connect(reuse_if_open=True)
    return db_path


def close_database() -> None:
    if not database.is_closed():
        database.close()
