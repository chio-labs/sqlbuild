"""Tests for microbatch lookback resolution."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.planner._helpers.output.plan_entry import resolve_microbatch_lookback
from sqlbuild.compiler.planner.types import IncrementalStrategy
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    MicrobatchLookbackTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import (
    build_microbatch_lookback_model,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchLookbackTestCase(
            description="delete_insert defaults to batch_size",
            incremental_strategy=IncrementalStrategy.DELETE_INSERT,
            batch_size="1d",
            lookback=None,
            expected_lookback="1d",
        ),
        MicrobatchLookbackTestCase(
            description="merge defaults to batch_size",
            incremental_strategy=IncrementalStrategy.MERGE,
            batch_size="6h",
            lookback=None,
            expected_lookback="6h",
        ),
        MicrobatchLookbackTestCase(
            description="append does not default to batch_size",
            incremental_strategy=IncrementalStrategy.APPEND,
            batch_size="1d",
            lookback=None,
            expected_lookback=None,
        ),
        MicrobatchLookbackTestCase(
            description="explicit lookback wins over batch_size",
            incremental_strategy=IncrementalStrategy.DELETE_INSERT,
            batch_size="1d",
            lookback="2d",
            expected_lookback="2d",
        ),
        MicrobatchLookbackTestCase(
            description="effective batch defaults to concrete effective grain size",
            incremental_strategy=IncrementalStrategy.DELETE_INSERT,
            batch_size="effective",
            lookback=None,
            expected_lookback="1mo",
            effective_grain="month",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_microbatch_model_when_resolving_lookback_then_returns_expected_value(
    test_case: MicrobatchLookbackTestCase,
) -> None:
    model: CompiledModel = build_microbatch_lookback_model(
        incremental_strategy=test_case.incremental_strategy,
        batch_size=test_case.batch_size,
        lookback=test_case.lookback,
    )

    result: str | None = resolve_microbatch_lookback(
        model=model, effective_grain=test_case.effective_grain
    )

    assert result == test_case.expected_lookback
