from __future__ import annotations

import pytest

from sqlbuild.compiler.source_freshness.exceptions import (
    SourceFreshnessObservationError as SharedSourceFreshnessObservationError,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessObservation as SharedSourceFreshnessObservation,
)
from sqlbuild.virtual.freshness.exceptions import (
    SourceFreshnessObservationError as VirtualSourceFreshnessObservationError,
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


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessCompatibilityTestCase(
            description="virtual observation error aliases shared error",
            expected_same_object=True,
        )
    ],
    ids=["virtual observation error aliases shared error"],
)
def test_given_virtual_observation_error_import_when_resolving_then_aliases_shared_error(
    test_case: VirtualSourceFreshnessCompatibilityTestCase,
) -> None:
    assert (
        VirtualSourceFreshnessObservationError is SharedSourceFreshnessObservationError
    ) == test_case.expected_same_object
