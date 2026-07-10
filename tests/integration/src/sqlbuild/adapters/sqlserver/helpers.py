from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.adapters.sqlserver.client import SqlServerAdapter


def build_unique_schema_name(*, prefix: str) -> str:
    suffix: str = uuid.uuid4().hex[:10]
    return f"{prefix}_{suffix}"


def qualified_name(*, schema: str, name: str) -> str:
    return f"[{schema}].[{name}]"


def fetch_rows(
    *, adapter: SqlServerAdapter, connection: Any, sql: str
) -> tuple[tuple[object, ...], ...]:
    cursor: Any = adapter.execute(connection, sql=sql)
    return tuple(tuple(row) for row in cursor.fetchall())


def build_statement_recorder() -> StatementRecorder:
    return StatementRecorder()


def write_seed_file(tmp_path: Path, contents: str) -> Path:
    path: Path = tmp_path / "seed.csv"
    path.write_text(contents, encoding="utf-8")
    return path
