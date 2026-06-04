from __future__ import annotations

from datetime import datetime

import pytest

from sqlbuild.compiler.source_freshness.main.data_version_hash import (
    source_freshness_data_version_hash,
)
from sqlbuild.compiler.source_freshness.main.normalization import (
    normalize_source_freshness_data_version,
)
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from tests.unit.src.sqlbuild.compiler.source_freshness.main._test_types import (
    SharedSourceFreshnessHashTestCase,
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
            observed_at=datetime(2026, 1, 15, 12, 0, 0),
            later_observed_at=datetime(2026, 1, 16, 12, 0, 0),
            expected_hash_changes_with_observed_at=False,
        )
    ],
    ids=["hash is stable and ignores observed_at"],
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
