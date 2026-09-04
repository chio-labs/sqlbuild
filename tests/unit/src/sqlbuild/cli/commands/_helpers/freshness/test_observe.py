from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

import pytest

from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.cli.commands._helpers.freshness.observe import (
    observe_source_freshness_for_command,
)
from sqlbuild.cli.commands.models import FreshnessCommandResult
from tests.unit.src.sqlbuild.cli.commands._helpers.freshness._test_types import (
    FreshnessObservationTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.freshness.helpers import (
    FreshnessRecordingAdapter,
    adapter_metadata_sources,
    freshness_sources,
    source_freshness_record,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FreshnessObservationTestCase(
            description="classifies observed unknown and error sources",
            select=(),
            exclude=(),
            expected_statuses={
                "raw_age_error": "observed",
                "raw_age_pass": "observed",
                "raw_age_unknown": "observed",
                "raw_age_warn": "observed",
                "raw_error": "error",
                "raw_lag": "observed",
                "raw_orders": "observed",
                "raw_payments": "observed",
                "raw_unknown": "unknown",
            },
            expected_versions={
                "raw_age_error": "2025-12-31T21:00:00+00:00",
                "raw_age_pass": "2025-12-31T23:30:00+00:00",
                "raw_age_unknown": "42",
                "raw_age_warn": "2025-12-31T22:30:00+00:00",
                "raw_lag": "2026-01-01T00:05:00+00:00",
                "raw_orders": "1",
                "raw_payments": "2",
            },
            expected_age_statuses={
                "raw_age_error": "error",
                "raw_age_pass": "pass",
                "raw_age_unknown": "unknown",
                "raw_age_warn": "warn",
            },
        ),
        FreshnessObservationTestCase(
            description="applies exact source selection and exclusion",
            select=("raw_orders", "raw_unknown"),
            exclude=("raw_unknown",),
            expected_statuses={"raw_orders": "observed"},
            expected_versions={"raw_orders": "1"},
            expected_age_statuses={},
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
                "raw_lag": "2026-01-01T00:05:00+00:00",
                "raw_orders": "1",
                "raw_payments": "2",
            },
            expected_age_statuses={},
        ),
    ],
    ids=lambda case: case.description,
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
        name: versions[name] for name in test_case.expected_versions
    } == test_case.expected_versions
    sources_by_age_status_presence: defaultdict[bool, list[str]] = defaultdict(list)
    for source in result.sources:
        sources_by_age_status_presence[source.age_status is not None].append(source.name)
    expected_age_statuses: dict[str, str] = test_case.expected_age_statuses or {}
    assert set(sources_by_age_status_presence[True]) == set(expected_age_statuses)
    sources_by_name: dict[str, Any] = {source.name: source for source in result.sources}
    assert len(sources_by_name) == len(result.sources)
    for name, expected_age_status in expected_age_statuses.items():
        age_status: Any = sources_by_name[name].age_status
        assert age_status is not None
        assert age_status.value == expected_age_status


@pytest.mark.parametrize(
    "test_case",
    [
        FreshnessObservationTestCase(
            description="adapter metadata freshness observes physical table source",
            select=("raw_metadata",),
            exclude=(),
            expected_statuses={"raw_metadata": "observed"},
            expected_versions={"raw_metadata": "2026-01-02T03:04:05+00:00"},
        )
    ],
    ids=lambda case: case.description,
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
