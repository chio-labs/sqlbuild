"""Helpers for fact cache store unit tests."""

from __future__ import annotations

import hashlib
import pickle
import sqlite3
from contextlib import closing
from pathlib import Path

from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore
from sqlbuild.spec.contracts.models import SourceLocation

FACT_NAMESPACE: str = "unit"
FACT_ALGORITHM: str = "unit-facts-v1"
FACT_VALUE: tuple[SourceLocation, ...] = (
    SourceLocation(path=Path("models/orders.sql"), line=3, column=5, end_line=3, end_column=12),
)


def fact_database(root: Path) -> Path:
    return next(root.rglob(f"{FACT_NAMESPACE}.sqlite3"))


def publish_fact(
    root: Path, *, key_parts: tuple[str, ...], slot: str, value: object = FACT_VALUE
) -> str:
    with FactCacheStore(root=root, namespace=FACT_NAMESPACE, algorithm=FACT_ALGORITHM) as store:
        key: str = store.key(*key_parts)
        store.stage(key=key, slot=slot, value=value)
    return key


def read_fact(
    root: Path | None,
    *,
    key_parts: tuple[str, ...],
    slot: str = "orders",
    algorithm: str = FACT_ALGORITHM,
) -> dict[str, object]:
    with FactCacheStore(root=root, namespace=FACT_NAMESPACE, algorithm=algorithm) as store:
        return store.read_many(((slot, store.key(*key_parts)),))


def stored_fact_slots(root: Path) -> list[str]:
    with closing(sqlite3.connect(fact_database(root))) as connection:
        rows: list[tuple[str]] = connection.execute(
            "SELECT slot FROM fact ORDER BY slot"
        ).fetchall()
    return [slot for (slot,) in rows]


def _overwrite_verified_payload(database: Path, payload: bytes) -> None:
    with closing(sqlite3.connect(database)) as connection, connection:
        cache_key: str = connection.execute("SELECT cache_key FROM fact").fetchone()[0]
        digest: str = hashlib.sha256(cache_key.encode() + b"\0" + payload).hexdigest()
        _ = connection.execute("UPDATE fact SET payload = ?, digest = ?", (payload, digest))


def flip_payload_byte(root: Path) -> None:
    database: Path = fact_database(root)
    with closing(sqlite3.connect(database)) as connection, connection:
        payload: bytes = connection.execute("SELECT payload FROM fact").fetchone()[0]
        _ = connection.execute("UPDATE fact SET payload = ?", (payload[:-1] + b"\x00",))


def write_untrusted_global(root: Path) -> None:
    _overwrite_verified_payload(fact_database(root), pickle.dumps(Path.home, protocol=5))


def truncate_verified_payload(root: Path) -> None:
    _overwrite_verified_payload(fact_database(root), b"\x80\x05")


def replace_database_with_garbage(root: Path) -> None:
    fact_database(root).write_bytes(b"not a sqlite database")
