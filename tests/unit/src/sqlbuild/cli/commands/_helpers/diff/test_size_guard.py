"""Default full diff limits and size guard error rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from sqlbuild.cli.commands._helpers.diff.size_guard import (
    build_diff_size_guard_error,
    resolve_full_diff_size_limits,
)
from sqlbuild.cli.commands.exceptions import DiffSizeGuardError
from sqlbuild.executor.diff.exceptions import FullDiffSizeGuardError
from sqlbuild.executor.diff.models import FullDiffSizeLimits
from tests.unit.src.sqlbuild.cli.commands._helpers.diff._test_types import (
    DiffSizeGuardErrorTestCase,
    FullDiffSizeLimitsTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.diff.helpers import (
    blocked_orders,
    diff_request,
    prod_dev_inputs,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FullDiffSizeLimitsTestCase(
            description="unset limits use the built-in default",
            full=False,
            schema_only=False,
            bounded=None,
            prod_max_full_rows=None,
            dev_max_full_rows=None,
            expected_limits=FullDiffSizeLimits(
                left_target="prod",
                right_target="dev",
                left_max_rows=10_000_000,
                right_max_rows=10_000_000,
            ),
        ),
        FullDiffSizeLimitsTestCase(
            description="each side uses its own target limit",
            full=False,
            schema_only=False,
            bounded=None,
            prod_max_full_rows=500,
            dev_max_full_rows="unlimited",
            expected_limits=FullDiffSizeLimits(
                left_target="prod", right_target="dev", left_max_rows=500, right_max_rows=None
            ),
        ),
        FullDiffSizeLimitsTestCase(
            description="explicit full bypasses the guard",
            full=True,
            schema_only=False,
            bounded=None,
            prod_max_full_rows=1,
            dev_max_full_rows=1,
            expected_limits=None,
        ),
        FullDiffSizeLimitsTestCase(
            description="explicit schema only bypasses the guard",
            full=False,
            schema_only=True,
            bounded=None,
            prod_max_full_rows=1,
            dev_max_full_rows=1,
            expected_limits=None,
        ),
        FullDiffSizeLimitsTestCase(
            description="explicit bounded bypasses the guard",
            full=False,
            schema_only=False,
            bounded="7d",
            prod_max_full_rows=1,
            dev_max_full_rows=1,
            expected_limits=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_mode_flags_and_target_limits_when_resolving_then_guard_limits_match(
    test_case: FullDiffSizeLimitsTestCase,
) -> None:
    limits: FullDiffSizeLimits | None = resolve_full_diff_size_limits(
        request=diff_request(
            full=test_case.full, schema_only=test_case.schema_only, bounded=test_case.bounded
        ),
        discovered_inputs=prod_dev_inputs(
            prod_max_full_rows=test_case.prod_max_full_rows,
            dev_max_full_rows=test_case.dev_max_full_rows,
        ),
        from_target="prod",
        to_target="dev",
    )

    assert limits == test_case.expected_limits


@pytest.mark.parametrize(
    "test_case",
    [
        DiffSizeGuardErrorTestCase(
            description="model with cursor offers bounded command",
            select=("orders",),
            unique_key_override=(),
            has_cursor=True,
            expected_full_command="sqb diff prod:dev --full --select orders",
            expected_bounded_command="sqb diff prod:dev --bounded <window> --select orders",
            expected_message_fragments=(
                "orders: prod 12,500,000 rows, limit 10,000,000; "
                "dev size unknown: no row count (view), limit 10,000,000",
                "Run one of these instead:",
                "sqb diff prod:dev --schema-only --select orders",
            ),
        ),
        DiffSizeGuardErrorTestCase(
            description="model without cursor omits bounded command and keeps key flags",
            select=("tag:daily", "path:models/marts"),
            unique_key_override=("order_id", "line number"),
            has_cursor=False,
            expected_full_command=(
                "sqb diff prod:dev --full --select tag:daily path:models/marts "
                "--key order_id 'line number'"
            ),
            expected_bounded_command=None,
            expected_message_fragments=("; no cursor",),
            expected_absent_fragments=("--bounded",),
        ),
        DiffSizeGuardErrorTestCase(
            description="project dir is a global flag placed before diff",
            select=("orders",),
            unique_key_override=(),
            has_cursor=False,
            expected_full_command=(
                "sqb --project-dir projects/shop diff prod:dev --full --select orders"
            ),
            expected_bounded_command=None,
            expected_message_fragments=(),
            project_dir=Path("projects/shop"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_blocked_models_when_building_guard_error_then_names_sizes_and_commands(
    test_case: DiffSizeGuardErrorTestCase,
) -> None:
    error: DiffSizeGuardError = build_diff_size_guard_error(
        request=diff_request(
            select=test_case.select,
            unique_key_override=test_case.unique_key_override,
            project_dir=test_case.project_dir,
        ),
        from_target="prod",
        to_target="dev",
        error=FullDiffSizeGuardError(
            "full diff stopped", blocked=blocked_orders(has_cursor=test_case.has_cursor)
        ),
    )

    assert error.code == "C270"
    assert error.exit_code == 2
    assert error.status == "incomplete"
    assert test_case.expected_full_command in error.message
    fragment: str
    for fragment in test_case.expected_message_fragments:
        assert fragment in error.message
    for fragment in test_case.expected_absent_fragments:
        assert fragment not in error.message
        assert fragment not in str(error.help)
    commands: dict[str, Any] = cast(dict[str, Any], error.details["commands"])
    assert commands["full"] == test_case.expected_full_command
    assert commands["bounded"] == test_case.expected_bounded_command
    models: list[dict[str, Any]] = cast(list[dict[str, Any]], error.details["models"])
    assert models[0]["from"]["row_count"] == 12_500_000
    assert models[0]["to"]["row_count"] is None
    assert models[0]["to"]["exceeds_limit"] is True
    assert "targets.prod.diff.max_full_rows and targets.dev.diff.max_full_rows" in str(error.help)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
