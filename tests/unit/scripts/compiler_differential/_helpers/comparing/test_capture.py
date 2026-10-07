"""Stage captures on disk are compared node by node with exact first-difference pointers."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.compiler_differential._helpers.comparing.capture import first_capture_difference
from scripts.compiler_differential.models import Divergence
from sqlbuild.compiler.frontier._helpers.stage_capture import render_stage_capture
from tests.unit.scripts.compiler_differential._helpers.comparing._test_types import (
    CaptureDifferenceTestCase,
    CapturePreviewTestCase,
    CaptureTextDifferenceTestCase,
)
from tests.unit.scripts.compiler_differential._helpers.comparing.helpers import (
    marker_shaped_orders,
    orders_batch,
    orders_batch_for_run,
    orders_batch_from_other_run,
    orders_batch_with_changed_line,
    orders_batch_without_last,
    store_paths,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CaptureDifferenceTestCase(
            description="identical_shared_captures",
            left=orders_batch,
            right=orders_batch,
            expected_location=None,
        ),
        CaptureDifferenceTestCase(
            description="change_inside_a_shared_node",
            left=orders_batch,
            right=lambda: orders_batch_with_changed_line(order_index=3, line_index=7),
            expected_location="/orders/3/lines/7/quantity",
        ),
        CaptureDifferenceTestCase(
            description="change_to_one_copy_of_a_repeated_node",
            left=orders_batch,
            right=lambda: orders_batch_with_changed_line(order_index=4, line_index=0),
            expected_location="/orders/4/lines/0/quantity",
        ),
        CaptureDifferenceTestCase(
            description="run_identity_inside_shared_nodes_is_masked",
            left=orders_batch_for_run,
            right=orders_batch_from_other_run,
            expected_location=None,
        ),
        CaptureDifferenceTestCase(
            description="large_set_elements_differing_only_in_masked_noise",
            left=lambda: store_paths(native_suffix="-native-v3"),
            right=lambda: store_paths(native_suffix=""),
            expected_location=None,
        ),
        CaptureDifferenceTestCase(
            description="authored_marker_shaped_data_is_not_a_reference",
            left=lambda: marker_shaped_orders(name="orders"),
            right=lambda: marker_shaped_orders(name="customers"),
            expected_location="/__mapping__/0/1",
        ),
        CaptureDifferenceTestCase(
            description="identical_marker_shaped_data",
            left=lambda: marker_shaped_orders(name="orders"),
            right=lambda: marker_shaped_orders(name="orders"),
            expected_location=None,
        ),
        CaptureDifferenceTestCase(
            description="shared_node_against_inline_value",
            left=orders_batch,
            right=lambda: {**orders_batch(), "orders": [{"order_id": 0}]},
            expected_location="/orders/0/lines",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_two_captures_when_comparing_then_first_logical_difference_is_reported(
    test_case: CaptureDifferenceTestCase, tmp_path: Path
) -> None:
    left: Path = tmp_path / "left.json"
    right: Path = tmp_path / "right.json"
    _ = left.write_text(render_stage_capture(test_case.left()), encoding="utf-8")
    _ = right.write_text(render_stage_capture(test_case.right()), encoding="utf-8")

    found: Divergence | None = first_capture_difference(left=left, right=right)

    assert getattr(found, "location", None) == test_case.expected_location


@pytest.mark.parametrize(
    "test_case",
    [
        CapturePreviewTestCase(
            description="missing_list_item_previews_the_resolved_node",
            left=orders_batch,
            right=orders_batch_without_last,
            expected_location="/orders/5",
            expected_left_prefix='{"order_id": 1, "lines": [{"sku": "product-0000"',
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_shared_value_when_comparing_then_preview_shows_its_content(
    test_case: CapturePreviewTestCase, tmp_path: Path
) -> None:
    left: Path = tmp_path / "left.json"
    right: Path = tmp_path / "right.json"
    _ = left.write_text(render_stage_capture(test_case.left()), encoding="utf-8")
    _ = right.write_text(render_stage_capture(test_case.right()), encoding="utf-8")

    found: Divergence | None = first_capture_difference(left=left, right=right)

    assert getattr(found, "location", None) == test_case.expected_location
    assert getattr(found, "left", "").startswith(test_case.expected_left_prefix)


@pytest.mark.parametrize(
    "test_case",
    [
        CaptureTextDifferenceTestCase(
            description="truncated_capture",
            left='{"orders": [\n1,\n2\n]}\n',
            right='{"orders": [\n1,\n3',
            expected_location="line 3",
        ),
        CaptureTextDifferenceTestCase(
            description="identical_invalid_captures",
            left="not json\n",
            right="not json\n",
            expected_location=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_capture_that_is_not_json_when_comparing_then_first_differing_line_is_reported(
    test_case: CaptureTextDifferenceTestCase, tmp_path: Path
) -> None:
    left: Path = tmp_path / "left.json"
    right: Path = tmp_path / "right.json"
    _ = left.write_text(test_case.left, encoding="utf-8")
    _ = right.write_text(test_case.right, encoding="utf-8")

    found: Divergence | None = first_capture_difference(left=left, right=right)

    assert getattr(found, "location", None) == test_case.expected_location


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
