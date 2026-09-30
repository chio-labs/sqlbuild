"""Background publication of fact rows in multi-row statements so writes rarely take the GIL."""

from __future__ import annotations

import sqlite3
import threading
import zlib
from contextlib import closing
from pathlib import Path

from sqlbuild.compiler.fact_cache.classes.fact_publication_registry import (
    FactPublicationRegistry,
)
from sqlbuild.compiler.fact_cache.constants import (
    FACT_CACHE_CREATE_TABLE_SQL,
    FACT_CACHE_INSERT_CHUNK_ROWS,
    FACT_CACHE_INSERT_ROW_SQL,
    FACT_CACHE_INSERT_SQL,
    FACT_CACHE_SQLITE_TIMEOUT_SECONDS,
    FACT_CACHE_WRITE_PRAGMAS,
    FACT_CACHE_WRITER_THREAD_NAME,
)

_PUBLICATIONS: FactPublicationRegistry = FactPublicationRegistry()


def publish_fact_rows(
    *, database_path: Path, rows: tuple[tuple[str, str, str, bytes], ...]
) -> None:
    """Publish (slot, key, digest, payload) rows after earlier publications to the same file."""

    def write(previous: threading.Thread | None) -> None:
        _write_rows(database_path=database_path, rows=rows, previous=previous)

    _PUBLICATIONS.start(
        database_path=database_path, write=write, thread_name=FACT_CACHE_WRITER_THREAD_NAME
    )


def await_fact_publication(*, database_path: Path | None = None) -> None:
    """Wait until pending publications to one database, or to every database, are durable."""

    _PUBLICATIONS.wait(database_path=database_path)


def entry_digest(*, cache_key: str, payload: bytes) -> str:
    """Return the CRC-32 checksum binding one payload to its exact cache key."""

    return f"{zlib.crc32(payload, zlib.crc32(cache_key.encode() + b'\0')):08x}"


def _write_rows(
    *,
    database_path: Path,
    rows: tuple[tuple[str, str, str, bytes], ...],
    previous: threading.Thread | None,
) -> None:
    if previous is not None:
        previous.join()
    try:
        _insert_records(database_path=database_path, records=rows)
    except sqlite3.DatabaseError as error:
        if type(error) is sqlite3.DatabaseError:
            _replace_unreadable_database(database_path=database_path, records=rows)
    except (sqlite3.Error, OSError):
        return


def _replace_unreadable_database(
    *, database_path: Path, records: tuple[tuple[str, str, str, bytes], ...]
) -> None:
    try:
        database_path.unlink(missing_ok=True)
        _insert_records(database_path=database_path, records=records)
    except (OSError, sqlite3.Error):
        return


def _insert_records(
    *, database_path: Path, records: tuple[tuple[str, str, str, bytes], ...]
) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        closing(
            sqlite3.connect(database_path, timeout=FACT_CACHE_SQLITE_TIMEOUT_SECONDS)
        ) as connection,
        connection,
    ):
        for pragma in FACT_CACHE_WRITE_PRAGMAS:
            _ = connection.execute(pragma)
        _ = connection.execute(FACT_CACHE_CREATE_TABLE_SQL)
        for start in range(0, len(records), FACT_CACHE_INSERT_CHUNK_ROWS):
            chunk: tuple[tuple[str, str, str, bytes], ...] = records[
                start : start + FACT_CACHE_INSERT_CHUNK_ROWS
            ]
            parameters: list[str | bytes] = []
            for record in chunk:
                parameters.extend(record)
            _ = connection.execute(
                FACT_CACHE_INSERT_SQL + ",".join([FACT_CACHE_INSERT_ROW_SQL] * len(chunk)),
                parameters,
            )
