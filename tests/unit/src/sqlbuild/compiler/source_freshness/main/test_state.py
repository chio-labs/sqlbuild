from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlbuild.compiler.source_freshness.main.data_version_hash import (
    source_freshness_data_version_hash,
)
from sqlbuild.compiler.source_freshness.main.normalization import (
    normalize_source_freshness_data_version,
)
from sqlbuild.compiler.source_freshness.main.record_equivalence import (
    source_freshness_records_equivalent,
)
from sqlbuild.compiler.source_freshness.models import SourceFreshnessRecord
from sqlbuild.spec.contracts.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from tests.unit.src.sqlbuild.compiler.source_freshness.main._test_types import (
    SharedSourceFreshnessHashTestCase,
    SourceFreshnessStateCompatibilityTestCase,
)
from tests.unit.src.sqlbuild.compiler.source_freshness.main.helpers import (
    timestamp_source_freshness_record,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SharedSourceFreshnessHashTestCase(
            description="hash is stable and ignores observed_at",
            source_name="raw.orders",
            strategy="column",
            value_kind="integer",
            data_version="42",
            observed_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
            later_observed_at=datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC),
            expected_hash_changes_with_observed_at=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_same_source_freshness_identity_when_hashing_then_ignores_observed_at(
    test_case: SharedSourceFreshnessHashTestCase,
) -> None:
    normalized_data_version: str = normalize_source_freshness_data_version(
        value=int(test_case.data_version),
        value_kind=SourceFreshnessValueKind(test_case.value_kind),
    )
    first_hash: str = source_freshness_data_version_hash(
        source_name=test_case.source_name,
        strategy=SourceFreshnessStrategy(test_case.strategy),
        value_kind=SourceFreshnessValueKind(test_case.value_kind),
        data_version=normalized_data_version,
    )
    second_hash: str = source_freshness_data_version_hash(
        source_name=test_case.source_name,
        strategy=SourceFreshnessStrategy(test_case.strategy),
        value_kind=SourceFreshnessValueKind(test_case.value_kind),
        data_version=normalized_data_version,
    )

    assert first_hash == second_hash
    assert test_case.expected_hash_changes_with_observed_at is False


@pytest.mark.parametrize(
    "test_case",
    (
        SourceFreshnessStateCompatibilityTestCase(
            description="legacy naive and aware UTC timestamp state are equivalent",
            previous_data_version="2026-01-15T12:00:00",
            current_data_version="2026-01-15T12:00:00+00:00",
            expected_equivalent=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_legacy_naive_timestamp_state_when_comparing_aware_state_then_matches_same_instant(
    test_case: SourceFreshnessStateCompatibilityTestCase,
) -> None:
    previous_record: SourceFreshnessRecord = timestamp_source_freshness_record(
        data_version=test_case.previous_data_version,
        data_version_hash="legacy-hash",
    )
    current_record: SourceFreshnessRecord = timestamp_source_freshness_record(
        data_version=test_case.current_data_version,
        data_version_hash="aware-hash",
    )

    equivalent: bool = source_freshness_records_equivalent(
        previous_record=previous_record,
        current_record=current_record,
    )

    assert equivalent is test_case.expected_equivalent
