"""Tests for seed pipeline execution helpers."""

from __future__ import annotations

import pytest

from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.pipeline.helpers.seeding import run_seed_pipeline
from tests.unit.src.sqlbuild.executor.pipeline.helpers._test_types import (
    SeedPipelineConcurrencyTestCase,
)
from tests.unit.src.sqlbuild.executor.pipeline.helpers.helpers import (
    SeedPipelineTestAdapter,
    build_seed_plan,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SeedPipelineConcurrencyTestCase(
            description="uses bounded concurrent connections and preserves seed result order",
            seed_names=("seed_a", "seed_b", "seed_c"),
            max_concurrency=2,
            expected_connection_count=2,
            expected_seed_order=("seed_a", "seed_b", "seed_c"),
        ),
    ],
    ids=["uses bounded concurrent connections and preserves seed result order"],
)
def test_given_multiple_seeds_when_running_seed_pipeline_then_uses_concurrent_connections(
    test_case: SeedPipelineConcurrencyTestCase,
) -> None:
    adapter: SeedPipelineTestAdapter = SeedPipelineTestAdapter()
    connection_starts: list[int] = []

    results: tuple[SeedExecutionResult, ...] = run_seed_pipeline(
        plan=build_seed_plan(seed_names=test_case.seed_names),
        connection_config={},
        adapter=adapter,
        max_concurrency=test_case.max_concurrency,
        on_connection_start=connection_starts.append,
    )

    assert connection_starts == [test_case.expected_connection_count]
    assert tuple(result.seed_name for result in results) == test_case.expected_seed_order
    assert len(adapter.connections) == test_case.expected_connection_count
    loads_by_target: dict[str, object] = dict(adapter.loads)
    assert loads_by_target["seed_a"] is not loads_by_target["seed_b"]
    assert adapter.closed_connections == adapter.connections
