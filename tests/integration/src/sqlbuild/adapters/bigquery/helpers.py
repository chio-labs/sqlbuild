"""Shared helpers for BigQuery integration tests."""

from __future__ import annotations

import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.shared.models import StatementRecorder, TableFreshnessMetadata
from sqlbuild.adapters.bigquery.client import BigQueryAdapter

_ENV_KEYS: tuple[str, ...] = ("SQB_TEST_BIGQUERY_PROJECT",)
_DEFAULT_LOCATION: str = "europe-west2"


def build_bigquery_connection_config(*, schema: str | None = None) -> dict[str, object]:
    """Return BigQuery connection config from required env vars or skip."""

    missing: list[str] = [key for key in _ENV_KEYS if not os.environ.get(key)]
    if missing:
        pytest.skip("BigQuery credentials not configured: " + ", ".join(sorted(missing)))
    return {
        "project": os.environ["SQB_TEST_BIGQUERY_PROJECT"],
        "location": os.environ.get("SQB_TEST_BIGQUERY_LOCATION", _DEFAULT_LOCATION),
        "schema": schema,
    }


def build_unique_dataset_name(*, prefix: str) -> str:
    """Build a BigQuery-safe unique dataset name."""

    normalized_prefix: str = re.sub(r"[^A-Za-z0-9_]", "_", prefix).lower().strip("_")
    suffix: str = uuid.uuid4().hex[:10].lower()
    return f"{normalized_prefix}_{suffix}"


def qualified_name(*, project: str, dataset: str, name: str) -> str:
    """Build a fully qualified BigQuery relation name."""

    return f"`{project}.{dataset}.{name}`"


def execute_statements(
    *,
    adapter: BigQueryAdapter,
    connection: Any,
    statements: tuple[str, ...],
) -> None:
    """Execute a sequence of SQL statements against BigQuery."""

    statement: str
    for statement in statements:
        adapter.execute(connection=connection, sql=statement)


def fetch_rows(
    *, adapter: BigQueryAdapter, connection: Any, sql: str
) -> tuple[tuple[object, ...], ...]:
    """Fetch all rows for a query."""

    cursor: Any = adapter.execute(connection=connection, sql=sql)
    try:
        return tuple(tuple(row) for row in cursor.fetchall())
    finally:
        cursor.close()


def write_seed_file(*, tmp_path: Path, filename: str, contents: str) -> Path:
    """Write a seed CSV file for BigQuery adapter tests."""

    file_path: Path = tmp_path / filename
    file_path.write_text(contents, encoding="utf-8")
    return file_path


def build_statement_recorder() -> StatementRecorder:
    """Build a statement recorder for adapter mutation operations."""

    return StatementRecorder()


def wait_for_bigquery_freshness_after(
    *,
    adapter: BigQueryAdapter,
    connection: Any,
    database: str,
    schema: str,
    name: str,
    previous_data_version: datetime,
) -> TableFreshnessMetadata:
    """Poll BigQuery table metadata until modified time advances."""

    metadata: TableFreshnessMetadata = adapter.get_table_freshness_metadata(
        connection=connection,
        database=database,
        schema=schema,
        name=name,
    )
    for _ in range(12):
        data_version: object = metadata.data_version
        if isinstance(data_version, datetime) and data_version > previous_data_version:
            return metadata
        time.sleep(5)
        metadata = adapter.get_table_freshness_metadata(
            connection=connection,
            database=database,
            schema=schema,
            name=name,
        )
    return metadata
