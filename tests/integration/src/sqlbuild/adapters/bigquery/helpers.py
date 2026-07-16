"""Shared helpers for BigQuery integration tests."""

from __future__ import annotations

import os
import re
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import TableFreshnessMetadata
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter

_ENV_KEYS: tuple[str, ...] = ("SQB_TEST_BIGQUERY_PROJECT",)
_DEFAULT_LOCATION: str = "europe-west2"


def _missing_env_key(key: str) -> tuple[str, ...]:
    return (key,)


def _present_env_key(key: str) -> tuple[str, ...]:
    del key
    return ()


def _skip_missing_env(missing: tuple[str, ...]) -> None:
    pytest.skip("BigQuery credentials not configured: " + ", ".join(sorted(missing)))


def _accept_env(missing: tuple[str, ...]) -> None:
    del missing


_ENV_KEY_RESULTS: MappingProxyType[bool, Callable[[str], tuple[str, ...]]] = MappingProxyType(
    {False: _missing_env_key, True: _present_env_key}
)
_ENV_VALIDATORS: MappingProxyType[bool, Callable[[tuple[str, ...]], None]] = MappingProxyType(
    {False: _accept_env, True: _skip_missing_env}
)


def build_bigquery_connection_config(*, schema: str | None = None) -> dict[str, object]:
    """Return BigQuery connection config from required env vars or skip."""

    missing: tuple[str, ...] = sum(
        (_ENV_KEY_RESULTS[bool(os.environ.get(key))](key) for key in _ENV_KEYS),
        (),
    )
    _ENV_VALIDATORS[bool(missing)](missing)
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
    try:
        for _ in range(12):
            data_version: object = metadata.data_version
            advanced: bool = (
                isinstance(data_version, datetime) and data_version > previous_data_version
            )
            _FRESHNESS_ACTIONS[advanced](metadata)
            time.sleep(5)
            metadata = adapter.get_table_freshness_metadata(
                connection=connection,
                database=database,
                schema=schema,
                name=name,
            )
    except _FreshnessAdvanced as advanced_result:
        return advanced_result.metadata
    return metadata


class _FreshnessAdvanced(Exception):
    def __init__(self, metadata: TableFreshnessMetadata) -> None:
        self.metadata = metadata


def _return_advanced_freshness(metadata: TableFreshnessMetadata) -> None:
    raise _FreshnessAdvanced(metadata)


def _continue_freshness_poll(metadata: TableFreshnessMetadata) -> None:
    del metadata


_FRESHNESS_ACTIONS: MappingProxyType[bool, Callable[[TableFreshnessMetadata], None]] = (
    MappingProxyType({False: _continue_freshness_poll, True: _return_advanced_freshness})
)
