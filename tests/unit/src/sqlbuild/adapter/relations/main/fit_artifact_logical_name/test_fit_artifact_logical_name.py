from __future__ import annotations

import hashlib

import pytest

from sqlbuild.adapter.relations.main.fit_artifact_logical_name import fit_artifact_logical_name
from sqlbuild.errors.contracts.exceptions import SharedInputError
from tests.unit.src.sqlbuild.adapter.relations.main.fit_artifact_logical_name._test_types import (
    FitArtifactLogicalNameErrorTestCase,
    FitArtifactLogicalNameTestCase,
)

LONG_NAME: str = "customer_orders_" + "x" * 40
LONG_NAME_HASH: str = hashlib.sha256(LONG_NAME.encode("utf-8")).hexdigest()[:8]


@pytest.mark.parametrize(
    "test_case",
    [
        FitArtifactLogicalNameTestCase(
            description="short name is kept unchanged",
            logical_name="orders",
            fixed_prefix="__prefix__",
            identifier_limit=63,
            expected_name="orders",
        ),
        FitArtifactLogicalNameTestCase(
            description="long name is shortened with a deterministic hash suffix",
            logical_name=LONG_NAME,
            fixed_prefix="__prefix__",
            identifier_limit=40,
            expected_name=f"{LONG_NAME[:21]}_{LONG_NAME_HASH}",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_logical_name_when_fitting_artifact_name_then_returns_expected_name(
    test_case: FitArtifactLogicalNameTestCase,
) -> None:
    fitted: str = fit_artifact_logical_name(
        logical_name=test_case.logical_name,
        fixed_prefix=test_case.fixed_prefix,
        identifier_limit=test_case.identifier_limit,
        artifact_label="Test artifact",
    )

    assert fitted == test_case.expected_name
    assert len(test_case.fixed_prefix + fitted) <= test_case.identifier_limit


@pytest.mark.parametrize(
    "test_case",
    [
        FitArtifactLogicalNameErrorTestCase(
            description="prefix longer than the limit is rejected",
            logical_name="orders",
            fixed_prefix="__a_prefix_that_is_too_long__",
            identifier_limit=10,
            expected_error_fragment="does not fit within identifier limit 10",
        ),
        FitArtifactLogicalNameErrorTestCase(
            description="room too small for a hash suffix is rejected",
            logical_name=LONG_NAME,
            fixed_prefix="__prefix__",
            identifier_limit=15,
            expected_error_fragment="cannot fit within identifier limit 15",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unfittable_name_when_fitting_artifact_name_then_raises_input_error(
    test_case: FitArtifactLogicalNameErrorTestCase,
) -> None:
    with pytest.raises(SharedInputError) as exc_info:
        fit_artifact_logical_name(
            logical_name=test_case.logical_name,
            fixed_prefix=test_case.fixed_prefix,
            identifier_limit=test_case.identifier_limit,
            artifact_label="Test artifact",
        )

    assert test_case.expected_error_fragment in str(exc_info.value)
