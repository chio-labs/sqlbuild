"""Cache-state changes applied between planner runs in migration fingerprint cache tests."""

from __future__ import annotations

import importlib.metadata
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild._native import fixture_inference_count
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile

ORDERS_SQL: str = 'SELECT o.order_id, o.amount_cents FROM __ref("stg_orders") AS o'
CURSOR_METADATA: str = json.dumps(
    {
        "model_name": "daily_orders",
        "config": {"materialized": "incremental", "cursor_inputs": {"order_events": "event_date"}},
    }
)
PLAIN_METADATA: str = json.dumps(
    {"model_name": "daily_orders", "config": {"materialized": "table"}}
)
DATABASE_GLOB: str = "migration-fingerprints-v*/migration-fingerprints.sqlite3"


def keep_cache(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave the persisted cache untouched."""

    del root, monkeypatch


def corrupt_database(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Overwrite the cache database with bytes that are not SQLite."""

    del monkeypatch
    next(root.glob(DATABASE_GLOB)).write_bytes(b"not a database")


def tamper_entries(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Change every stored fingerprint without updating its digest."""

    del monkeypatch
    connection: sqlite3.Connection = sqlite3.connect(next(root.glob(DATABASE_GLOB)))
    try:
        _ = connection.execute(
            'UPDATE migration_fingerprint SET payload = replace(payload, \'"f":"\', \'"f":"0\')'
        )
        connection.commit()
    finally:
        connection.close()


def replace_digests_with_non_ascii(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every stored digest with non-ASCII text, keeping the entry separator."""

    del monkeypatch
    connection: sqlite3.Connection = sqlite3.connect(next(root.glob(DATABASE_GLOB)))
    try:
        _ = connection.execute(
            "UPDATE migration_fingerprint "
            "SET payload = 'é' || substr(payload, instr(payload, char(10)))"
        )
        connection.commit()
    finally:
        connection.close()


def upgrade_sqlbuild(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Report a different installed sqlbuild version for the next run."""

    del root
    monkeypatch.setattr(importlib.metadata, "version", lambda package: f"{package}-next")


FIXTURE_PROFILES: dict[str, ExpressionInferenceProfile] = {
    "duckdb": ExpressionInferenceProfile(sql_analysis_dialect="duckdb"),
    "duckdb_again": ExpressionInferenceProfile(sql_analysis_dialect="duckdb"),
    "snowflake": ExpressionInferenceProfile(sql_analysis_dialect="snowflake"),
    "catalog": ExpressionInferenceProfile(sql_analysis_dialect="duckdb", binding_catalog=object()),
}
FIXTURE_QUERIES: dict[str, str] = {
    "orders": "SELECT 1 AS order_id, 'open' AS status UNION ALL SELECT 2, 'closed'",
    "customers": "SELECT 7 AS customer_id, NULL AS segment",
}


def reset_fixture_inference_count() -> None:
    """Start counting fixture inferences computed instead of reused from zero."""

    fixture_inference_count(reset=True)


class SqlTestsProject:
    """A project whose SQL tests are read through a callback each time planning asks for them."""

    def __init__(self, read_tests: Callable[[], tuple[object, ...]]) -> None:
        self._read_tests: Callable[[], tuple[object, ...]] = read_tests

    @property
    def sql_tests(self) -> tuple[object, ...]:
        return self._read_tests()
