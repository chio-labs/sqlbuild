"""Unit tests for the compile check that rejects cursor models without inputs (P011)."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.config.cursor_inputs import (
    cursor_model_without_inputs_diagnostics,
)
from sqlbuild.compiler.compile.models import CompilerDiagnostic
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    CursorModelWithoutInputsCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    cursor_model_input,
    diagnostic_spans,
)

_CURSOR_CONFIG: dict[str, object] = {
    "materialized": "incremental",
    "incremental_strategy": "delete_insert",
    "cursor": "revenue_date",
    "cursor_type": "timestamp",
    "cursor_grain": "day",
}
_CURSOR_LOCATION: tuple[str, int, int, int] = ("models/finance/daily_revenue.sql", 5, 3, 22)
_MESSAGE: str = (
    "incremental model 'daily_revenue' reads no inputs, so builds after the first "
    "cannot work out their cursor window"
)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorModelWithoutInputsCase(
            description="cursor model reading only constants",
            config=_CURSOR_CONFIG,
            reference_kinds=(),
            expected_codes=("P011",),
            expected_locations=(_CURSOR_LOCATION,),
        ),
        CursorModelWithoutInputsCase(
            description="cursor model calling only a function",
            config=_CURSOR_CONFIG,
            reference_kinds=("udf",),
            expected_codes=("P011",),
            expected_locations=(_CURSOR_LOCATION,),
        ),
        CursorModelWithoutInputsCase(
            description="cursor model reading a ref",
            config=_CURSOR_CONFIG,
            reference_kinds=("ref",),
            expected_codes=(),
        ),
        CursorModelWithoutInputsCase(
            description="cursor model reading a source",
            config=_CURSOR_CONFIG,
            reference_kinds=("source",),
            expected_codes=(),
        ),
        CursorModelWithoutInputsCase(
            description="cursor model reading a seed",
            config=_CURSOR_CONFIG,
            reference_kinds=("seed",),
            expected_codes=(),
        ),
        CursorModelWithoutInputsCase(
            description="cursor model with declared cursor inputs",
            config={**_CURSOR_CONFIG, "cursor_inputs": {"payments": "paid_at"}},
            reference_kinds=(),
            expected_codes=(),
        ),
        CursorModelWithoutInputsCase(
            description="rolling window microbatch model",
            config={
                **_CURSOR_CONFIG,
                "incremental_mode": "microbatch",
                "microbatch_strategy": "rolling_window",
            },
            reference_kinds=(),
            expected_codes=(),
        ),
        CursorModelWithoutInputsCase(
            description="incremental model without a cursor",
            config={"materialized": "incremental", "incremental_strategy": "append"},
            reference_kinds=(),
            expected_codes=(),
        ),
        CursorModelWithoutInputsCase(
            description="table model",
            config={"materialized": "table"},
            reference_kinds=(),
            expected_codes=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_inputs_when_checking_cursor_inputs_then_reports_p011_only_without_inputs(
    test_case: CursorModelWithoutInputsCase,
) -> None:
    diagnostics: tuple[CompilerDiagnostic, ...] = cursor_model_without_inputs_diagnostics(
        model_inputs=(
            cursor_model_input(config=test_case.config, reference_kinds=test_case.reference_kinds),
        )
    )

    assert tuple(diagnostic.code for diagnostic in diagnostics) == test_case.expected_codes
    assert all(diagnostic.message == _MESSAGE for diagnostic in diagnostics)
    assert all(
        "__ref(), __source() or __seed()" in (diagnostic.help or "") for diagnostic in diagnostics
    )
    assert diagnostic_spans(diagnostics) == test_case.expected_locations
