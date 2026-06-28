from __future__ import annotations

import pytest

from sqlbuild.shared.helpers.prephase_progress import format_prephase_cause_annotation
from tests.unit.src.sqlbuild.shared.helpers._test_types import PrephaseCauseAnnotationTestCase

PREPHASE_CAUSE_ANNOTATION_TEST_CASES: tuple[PrephaseCauseAnnotationTestCase, ...] = (
    PrephaseCauseAnnotationTestCase(
        description="formats one selected model cause",
        caused_by_names=("fact_orders",),
        expected_annotation="  [for fact_orders]",
    ),
    PrephaseCauseAnnotationTestCase(
        description="sorts and caps selected model causes at four",
        caused_by_names=(
            "mart_activity",
            "dim_customer",
            "fact_orders",
            "mart_revenue",
            "mart_retention",
            "mart_profit",
        ),
        expected_annotation=(
            "  [for dim_customer, fact_orders, mart_activity, mart_profit and 2 more]"
        ),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    PREPHASE_CAUSE_ANNOTATION_TEST_CASES,
    ids=[case.description for case in PREPHASE_CAUSE_ANNOTATION_TEST_CASES],
)
def test_given_selected_model_causes_when_formatting_then_uses_bracketed_capped_annotation(
    test_case: PrephaseCauseAnnotationTestCase,
) -> None:
    result: str = format_prephase_cause_annotation(test_case.caused_by_names)

    assert result == test_case.expected_annotation
