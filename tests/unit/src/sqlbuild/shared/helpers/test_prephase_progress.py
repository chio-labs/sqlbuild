from __future__ import annotations

import pytest

from sqlbuild.executor.clone.main.prephase_cause_annotation import (
    format_prephase_cause_annotation,
)
from sqlbuild.executor.clone.main.prephase_row_from_clone_item import (
    prephase_row_from_clone_item,
)
from sqlbuild.executor.clone.models import CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.shared.models import PrephaseProgressRow
from tests.unit.src.sqlbuild.shared.helpers._test_types import (
    PrephaseCauseAnnotationTestCase,
    PrephaseCloneItemRowTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
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
    ),
    ids=lambda case: case.description,
)
def test_given_selected_model_causes_when_formatting_then_uses_bracketed_capped_annotation(
    test_case: PrephaseCauseAnnotationTestCase,
) -> None:
    result: str = format_prephase_cause_annotation(test_case.caused_by_names)

    assert result == test_case.expected_annotation


@pytest.mark.parametrize(
    "test_case",
    (
        PrephaseCloneItemRowTestCase(
            description="maps cloned item to clone OK row",
            action="cloned",
            status="success",
            expected_label="clone",
            expected_status="OK",
        ),
        PrephaseCloneItemRowTestCase(
            description="maps copied item to copy WARN row",
            action="copied",
            status="warning",
            expected_label="copy",
            expected_status="WARN",
        ),
        PrephaseCloneItemRowTestCase(
            description="maps recreated view item to view FAIL row",
            action="recreated_view",
            status="failed",
            expected_label="view",
            expected_status="FAIL",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_clone_item_when_building_prephase_row_then_uses_shared_label_and_status(
    test_case: PrephaseCloneItemRowTestCase,
) -> None:
    row: PrephaseProgressRow = prephase_row_from_clone_item(
        item=CloneItemResult(
            name="example_model",
            action=CloneAction(test_case.action),
            status=CloneStatus(test_case.status),
            duration_seconds=1.25,
        ),
        caused_by_names=("selected_model",),
    )

    assert row.label == test_case.expected_label
    assert row.status == test_case.expected_status
    assert row.name == "example_model"
    assert row.caused_by_names == ("selected_model",)
