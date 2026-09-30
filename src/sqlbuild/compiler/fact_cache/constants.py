"""Stable constants for the local compile fact cache."""

from __future__ import annotations

FACT_CACHE_VERSION: int = 1
FACT_CACHE_DIRECTORY_PREFIX: str = "facts-v"
FACT_CACHE_DATABASE_SUFFIX: str = ".sqlite3"
FACT_CACHE_DIGEST_BYTES: int = 32
FACT_CACHE_MAX_ENTRY_BYTES: int = 16 * 1024 * 1024
FACT_CACHE_SQLITE_TIMEOUT_SECONDS: float = 0.1
FACT_CACHE_QUERY_CHUNK_SIZE: int = 500
FACT_CACHE_PICKLE_PROTOCOL: int = 5
FACT_CACHE_CREATE_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS fact (
    slot TEXT PRIMARY KEY,
    cache_key TEXT NOT NULL,
    digest TEXT NOT NULL,
    payload BLOB NOT NULL
)
"""
FACT_CACHE_INSERT_SQL: str = (
    "INSERT OR REPLACE INTO fact (slot, cache_key, digest, payload) VALUES "
)
FACT_CACHE_INSERT_ROW_SQL: str = "(?, ?, ?, ?)"
FACT_CACHE_PARAMETERS_PER_ROW: int = 4
SQLITE_PRE_3_32_MAX_BOUND_PARAMETERS: int = 999
FACT_CACHE_INSERT_CHUNK_ROWS: int = (
    SQLITE_PRE_3_32_MAX_BOUND_PARAMETERS // FACT_CACHE_PARAMETERS_PER_ROW
)
FACT_CACHE_WRITE_PRAGMAS: tuple[str, ...] = (
    "PRAGMA synchronous = OFF",
    "PRAGMA journal_mode = MEMORY",
)
FACT_CACHE_WRITER_THREAD_NAME: str = "sqlbuild-fact-cache-writer"
FACT_CACHE_ALLOWED_PACKAGE: str = "sqlbuild"
FACT_CACHE_ALLOWED_GLOBALS: frozenset[tuple[str, str]] = frozenset(
    {
        ("pathlib", "Path"),
        ("pathlib", "PosixPath"),
        ("pathlib", "PurePath"),
        ("pathlib", "PurePosixPath"),
        ("pathlib", "PureWindowsPath"),
        ("pathlib", "WindowsPath"),
        ("pathlib._local", "Path"),
        ("pathlib._local", "PosixPath"),
        ("pathlib._local", "PurePath"),
        ("pathlib._local", "PurePosixPath"),
        ("pathlib._local", "PureWindowsPath"),
        ("pathlib._local", "WindowsPath"),
        ("decimal", "Decimal"),
        ("datetime", "date"),
        ("datetime", "datetime"),
        ("datetime", "time"),
        ("datetime", "timedelta"),
        ("datetime", "timezone"),
        ("builtins", "frozenset"),
        ("builtins", "set"),
        ("builtins", "complex"),
        ("collections", "OrderedDict"),
    }
)
