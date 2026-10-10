"""Native model validators raise the exact error, code and help for invalid configs."""

from __future__ import annotations

import pytest

from tests.integration.src.sqlbuild.compiler.compile.native_model_config._test_types import (
    NativeErrorTestCase,
)
from tests.integration.src.sqlbuild.compiler.compile.native_model_config.helpers import (
    header_help,
    validation_outcome,
)

_INCREMENTAL: dict[str, object] = {
    "materialized": "incremental",
    "incremental_strategy": "append",
    "cursor": "updated_at",
    "cursor_type": "timestamp",
    "cursor_grain": "day",
}


@pytest.mark.parametrize(
    "test_case",
    [
        NativeErrorTestCase(
            description="a start bound shifted before year 1 in UTC",
            values={
                **_INCREMENTAL,
                "cursor_start": "0001-01-01T00:00:00+01:00",
                "cursor_end": "2024-01-01",
            },
            expected_outcome=(
                "CompileInputError",
                "model 'orders_daily': cursor_start value '0001-01-01T00:00:00+01:00' falls "
                "outside years 1-9999 once converted to UTC",
                "P001",
                header_help(
                    purpose="keep cursor_start within years 1-9999 in UTC",
                    entry="cursor_start '0001-01-01T00:00:00+00:00'",
                ),
            ),
        ),
        NativeErrorTestCase(
            description="an end bound shifted past year 9999 in UTC",
            values={
                **_INCREMENTAL,
                "cursor_start": "2024-01-01",
                "cursor_end": "9999-12-31T23:59:30.5-01:00",
            },
            expected_outcome=(
                "CompileInputError",
                "model 'orders_daily': cursor_end value '9999-12-31T23:59:30.5-01:00' falls "
                "outside years 1-9999 once converted to UTC",
                "P001",
                header_help(
                    purpose="keep cursor_end within years 1-9999 in UTC",
                    entry="cursor_end '9999-12-31T23:59:30.500000+00:00'",
                ),
            ),
        ),
        NativeErrorTestCase(
            description="an invalid replay policy with its header help",
            values={**_INCREMENTAL, "replay_on_change": "bounded-soon"},
            expected_outcome=(
                "CompileInputError",
                "model 'orders_daily': replay_on_change 'bounded-soon' has an invalid duration "
                "'soon'; use a positive duration such as 14d, 12h or 1mo",
                "P001",
                header_help(
                    purpose="use a valid replay_on_change", entry="replay_on_change bounded-14d"
                ),
            ),
        ),
        NativeErrorTestCase(
            description="a non-string materialization",
            values={"materialized": 5},
            expected_outcome=(
                "ConfigValueTypeError",
                "config key 'materialized' expected a string, got int",
                None,
                None,
            ),
        ),
        NativeErrorTestCase(
            description="an old-name view that is not a duration",
            values={"materialized": "table", "old_name_view": "soon"},
            expected_outcome=(
                "CompileInputError",
                "model 'orders_daily': old_name_view must be a positive duration such as 7d, or "
                "false; got 'soon'",
                "P001",
                "write for example old_name_view 7d, or old_name_view false",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_configs_when_validating_then_native_raises_the_exact_error(
    test_case: NativeErrorTestCase,
) -> None:
    assert validation_outcome(values=test_case.values) == test_case.expected_outcome


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
