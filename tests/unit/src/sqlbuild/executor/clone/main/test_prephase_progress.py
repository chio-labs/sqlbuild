from __future__ import annotations

import pytest

from sqlbuild.executor.clone.main._prephase_row_from_clone_item import (
    prephase_row_from_clone_item,
)
from sqlbuild.executor.clone.models import CloneItemResult, PrephaseProgressRow
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from tests.unit.src.sqlbuild.executor.clone.main._test_types import (
    PrephaseCloneItemRowTestCase,
)


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
        PrephaseCloneItemRowTestCase(
            description="maps recreated function item to function OK row",
            action="recreated_function",
            status="success",
            expected_label="function",
            expected_status="OK",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_clone_item_when_building_prephase_row_then_uses_clone_label_and_status(
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
