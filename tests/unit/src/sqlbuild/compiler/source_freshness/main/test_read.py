from __future__ import annotations

from datetime import datetime

import pytest

from sqlbuild.compiler.source_freshness.exceptions import SourceFreshnessInputError
from sqlbuild.compiler.source_freshness.main.read import read_latest_source_freshness
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
    SourceFreshnessSet,
)
from tests.unit.src.sqlbuild.compiler.source_freshness.main._test_types import (
    ReadLatestSourceFreshnessErrorTestCase,
    ReadLatestSourceFreshnessTestCase,
)
from tests.unit.src.sqlbuild.compiler.source_freshness.main.helpers import (
    FakeSourceFreshnessExecute,
    freshness_table_relation_exists,
    render_qualified_name,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReadLatestSourceFreshnessTestCase(
            description="parses observed_at from string rows",
            rows=[
                (
                    "raw.orders",
                    None,
                    "raw",
                    "orders",
                    "run_001",
                    "adapter_metadata",
                    "timestamp",
                    "2026-01-15T12:00:00",
                    "hash_orders",
                    "2026-01-15T12:05:00",
                )
            ],
            expected_source_name="raw.orders",
            expected_observed_at_iso="2026-01-15T12:05:00",
        )
    ],
    ids=["parses observed_at from string rows"],
)
def test_given_string_timestamp_row_when_reading_source_freshness_then_parses_timestamp(
    test_case: ReadLatestSourceFreshnessTestCase,
) -> None:
    result: SourceFreshnessSet = read_latest_source_freshness(
        connection=object(),
        execute=FakeSourceFreshnessExecute(rows=test_case.rows),
        relation_exists=freshness_table_relation_exists,
        database=None,
        schema="main",
        render_qualified_name=render_qualified_name,
    )

    identity: SourceFreshnessIdentity = SourceFreshnessIdentity(
        test_case.expected_source_name, None, "raw", "orders"
    )
    record: SourceFreshnessRecord = result.records[identity]
    assert record.observed_at == datetime.fromisoformat(test_case.expected_observed_at_iso)


@pytest.mark.parametrize(
    "test_case",
    [
        ReadLatestSourceFreshnessErrorTestCase(
            description="old source freshness table schema read failure gives operator guidance",
            read_error=RuntimeError("missing column data_version_hash"),
            expected_message_fragment="delete or rebuild the SQLBuild source freshness table",
        )
    ],
    ids=["old source freshness table schema read failure gives operator guidance"],
)
def test_given_read_failure_when_reading_source_freshness_then_raises_operator_guidance(
    test_case: ReadLatestSourceFreshnessErrorTestCase,
) -> None:
    with pytest.raises(SourceFreshnessInputError) as exc_info:
        read_latest_source_freshness(
            connection=object(),
            execute=FakeSourceFreshnessExecute(rows=[], read_error=test_case.read_error),
            relation_exists=freshness_table_relation_exists,
            database=None,
            schema="main",
            render_qualified_name=render_qualified_name,
        )

    assert test_case.expected_message_fragment in str(exc_info.value)
