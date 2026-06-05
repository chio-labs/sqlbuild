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
    freshness_sources,
)

FRESHNESS_OBSERVATION_TEST_CASES: list[FreshnessObservationTestCase] = [
    FreshnessObservationTestCase(
        description="classifies observed unknown and error sources",
        select=(),
        exclude=(),
        expected_statuses={
            "raw_error": "error",
            "raw_orders": "observed",
            "raw_payments": "observed",
            "raw_unknown": "unknown",
        },
        expected_versions={"raw_orders": "1", "raw_payments": "2"},
    ),
    FreshnessObservationTestCase(
        description="applies exact source selection and exclusion",
        select=("raw_orders", "raw_unknown"),
        exclude=("raw_unknown",),
        expected_statuses={"raw_orders": "observed"},
        expected_versions={"raw_orders": "1"},
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
    )

    statuses: dict[str, str] = {source.name: source.status for source in result.sources}
    versions: dict[str, str] = {
        source.name: source.current_data_version or "" for source in result.sources
    }
    assert statuses == test_case.expected_statuses
    assert {
        name: version for name, version in versions.items() if name in test_case.expected_versions
    } == test_case.expected_versions
