from __future__ import annotations

import pytest

from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessObservation as SharedSourceFreshnessObservation,
)
from sqlbuild.virtual.freshness.models import (
    SourceFreshnessObservation as VirtualSourceFreshnessObservation,
)
from tests.unit.src.sqlbuild.virtual.freshness._test_types import (
    VirtualSourceFreshnessCompatibilityTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessCompatibilityTestCase(
            description="virtual observation model aliases shared model",
            expected_same_object=True,
        )
    ],
    ids=["virtual observation model aliases shared model"],
)
def test_given_virtual_observation_model_import_when_resolving_then_aliases_shared_model(
    test_case: VirtualSourceFreshnessCompatibilityTestCase,
) -> None:
    assert (
        VirtualSourceFreshnessObservation is SharedSourceFreshnessObservation
    ) == test_case.expected_same_object
