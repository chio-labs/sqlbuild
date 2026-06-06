from __future__ import annotations

from typing import cast

import pytest

from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.cli.commands.main.helpers.freshness.models import FreshnessCommandResult
from sqlbuild.cli.commands.main.helpers.freshness.observe import (
    observe_source_freshness_for_command,
)
from tests.unit.src.sqlbuild.cli.commands.main.helpers.freshness._test_types import (
    FreshnessObservationTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.helpers.freshness.helpers import (
    FreshnessRecordingAdapter,
    adapter_metadata_sources,
    freshness_sources,
    source_freshness_record,
)

FRESHNESS_OBSERVATION_TEST_CASES: list[FreshnessObservationTestCase] = [
    FreshnessObservationTestCase(
        description="classifies observed unknown and error sources",
        select=(),
        exclude=(),
        expected_statuses={
            "raw_error": "error",
            "raw_lag": "observed",
            "raw_orders": "observed",
            "raw_payments": "observed",
            "raw_unknown": "unknown",
        },
        expected_versions={
            "raw_lag": "2026-01-01T00:05:00",
            "raw_orders": "1",
            "raw_payments": "2",
        },
    ),
    FreshnessObservationTestCase(
        description="applies exact source selection and exclusion",
        select=("raw_orders", "raw_unknown"),
        exclude=("raw_unknown",),
        expected_statuses={"raw_orders": "observed"},
        expected_versions={"raw_orders": "1"},
    ),
    FreshnessObservationTestCase(
        description="compares current observations to previous state",
        select=("raw_orders", "raw_payments", "raw_lag", "raw_unknown", "raw_error"),
        exclude=(),
        previous_records={
            source_freshness_record(
                source_name="raw_orders",
                data_version="1",
            ).identity: source_freshness_record(
                source_name="raw_orders",
                data_version="1",
            ),
            source_freshness_record(
                source_name="raw_payments", data_version="1", data_version_hash="old-hash"
            ).identity: source_freshness_record(
                source_name="raw_payments", data_version="1", data_version_hash="old-hash"
            ),
            source_freshness_record(
                source_name="raw_lag",
                value_kind="timestamp",
                data_version="2026-01-01T00:00:00",
                data_version_hash="old-timestamp-hash",
            ).identity: source_freshness_record(
                source_name="raw_lag",
                value_kind="timestamp",
                data_version="2026-01-01T00:00:00",
                data_version_hash="old-timestamp-hash",
            ),
        },
        expected_statuses={
            "raw_error": "error",
            "raw_lag": "tolerated",
            "raw_orders": "unchanged",
            "raw_payments": "changed",
            "raw_unknown": "unknown",
        },
        expected_versions={
            "raw_lag": "2026-01-01T00:05:00",
            "raw_orders": "1",
            "raw_payments": "2",
        },
    ),
]


@pytest.mark.parametrize(
    "test_case",
    FRESHNESS_OBSERVATION_TEST_CASES,
    ids=[case.description for case in FRESHNESS_OBSERVATION_TEST_CASES],
)
def test_given_sources_when_observing_freshness_then_classifies_sources(
    test_case: FreshnessObservationTestCase,
) -> None:
    adapter: FreshnessRecordingAdapter = FreshnessRecordingAdapter()

    result: FreshnessCommandResult = observe_source_freshness_for_command(
        adapter=cast(StrictAdapter, adapter),
        connection=object(),
        sources=freshness_sources(),
        select=test_case.select,
        exclude=test_case.exclude,
        observed_at=test_case.observed_at,
        previous_records=test_case.previous_records,
    )

    statuses: dict[str, str] = {source.name: source.status for source in result.sources}
    versions: dict[str, str] = {
        source.name: source.current_data_version or "" for source in result.sources
    }
    assert statuses == test_case.expected_statuses
    assert {
        name: version for name, version in versions.items() if name in test_case.expected_versions
    } == test_case.expected_versions


@pytest.mark.parametrize(
    "test_case",
    [
        FreshnessObservationTestCase(
            description="adapter metadata freshness observes physical table source",
            select=("raw_metadata",),
            exclude=(),
            expected_statuses={"raw_metadata": "observed"},
            expected_versions={"raw_metadata": "2026-01-02T03:04:05"},
        )
    ],
    ids=["adapter metadata freshness observes physical table source"],
)
def test_given_adapter_metadata_source_when_observing_freshness_then_uses_table_metadata(
    test_case: FreshnessObservationTestCase,
) -> None:
    adapter: FreshnessRecordingAdapter = FreshnessRecordingAdapter(table_metadata_supported=True)

    result: FreshnessCommandResult = observe_source_freshness_for_command(
        adapter=cast(StrictAdapter, adapter),
        connection=object(),
        sources=adapter_metadata_sources(),
        select=test_case.select,
        exclude=test_case.exclude,
        observed_at=test_case.observed_at,
        previous_records=test_case.previous_records,
    )

    statuses: dict[str, str] = {source.name: source.status for source in result.sources}
    versions: dict[str, str] = {
        source.name: source.current_data_version or "" for source in result.sources
    }
    assert statuses == test_case.expected_statuses
    assert versions == test_case.expected_versions
    assert adapter.metadata_requests == [("analytics", "raw", "orders")]
    assert adapter.queries == []
