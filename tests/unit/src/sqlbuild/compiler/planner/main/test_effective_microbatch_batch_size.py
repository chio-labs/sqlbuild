from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.main.execution.effective_microbatch_batch_size import (
    resolve_effective_microbatch_batch_size,
)
from sqlbuild.compiler.planner.types import CursorGrain
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import (
    EffectiveMicrobatchBatchSizeTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        EffectiveMicrobatchBatchSizeTestCase(
            description="day batch coarsens to month effective grain",
            batch_size="1d",
            effective_grain=CursorGrain.MONTH,
            expected_batch_size="1mo",
        ),
        EffectiveMicrobatchBatchSizeTestCase(
            description="month plus day compound retains its complete duration",
            batch_size="1mo1d",
            effective_grain=CursorGrain.MONTH,
            expected_batch_size="1mo1d",
        ),
        EffectiveMicrobatchBatchSizeTestCase(
            description="year plus day compound is not shortened to month",
            batch_size="1y1d",
            effective_grain=CursorGrain.MONTH,
            expected_batch_size="1y1d",
        ),
        EffectiveMicrobatchBatchSizeTestCase(
            description="hour plus minute compound coarsens to day",
            batch_size="1h30m",
            effective_grain=CursorGrain.DAY,
            expected_batch_size="1d",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_batch_duration_when_resolving_effective_grain_then_preserves_or_coarsens(
    test_case: EffectiveMicrobatchBatchSizeTestCase,
) -> None:
    result: str = resolve_effective_microbatch_batch_size(
        batch_size=test_case.batch_size,
        effective_grain=test_case.effective_grain,
    )

    assert result == test_case.expected_batch_size
