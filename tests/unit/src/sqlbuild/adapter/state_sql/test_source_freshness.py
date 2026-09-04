"""Golden SQL tests for adapter-owned source freshness state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sqlbuild.adapter.state_sql._helpers.source_freshness import (
    render_insert_source_freshness_records_sql,
)
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.source_freshness.models import SourceFreshnessRecord
from tests.unit.src.sqlbuild.adapter.state_sql._test_types import StateSqlGoldenTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        StateSqlGoldenTestCase(
            description="representative source freshness insert",
            expected_sql=(
                "INSERT INTO analytics._sqlbuild_source_freshness (source_name, "
                "target_database, target_schema, target_name, run_id, strategy, value_kind, "
                "data_version, data_version_hash, observed_at) VALUES ('raw.o''rders', NULL, "
                "'raw', 'orders', 'run-1', 'adapter', 'timestamp', "
                "'2026-01-01T01:00:00+01:00', 'hash', '2026-01-01T00:00:00+00:00')"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_representative_freshness_record_when_rendering_then_sql_matches_golden(
    test_case: StateSqlGoldenTestCase,
) -> None:
    sql: str = render_insert_source_freshness_records_sql(
        database=None,
        schema="analytics",
        records=(
            SourceFreshnessRecord(
                source_name="raw.o'rders",
                target_database=None,
                target_schema="raw",
                target_name="orders",
                run_id="run-1",
                strategy="adapter",
                value_kind="timestamp",
                data_version="2026-01-01T01:00:00+01:00",
                data_version_hash="hash",
                observed_at=datetime(2026, 1, 1, 1, tzinfo=timezone(timedelta(hours=1))),
            ),
        ),
        render_qualified_name=DuckDbAdapter().render_qualified_name,
    )

    assert sql == test_case.expected_sql


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
