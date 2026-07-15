"""Tests for pre-connection external source-load execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.compiler.planner.models import PlanOutput, SourceLoadPlanEntry
from sqlbuild.executor.build._helpers.external_source_loads import (
    run_external_source_loads_before_connections,
)
from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildRuntimeParams,
    ExternalSourceLoadResults,
)
from sqlbuild.executor.contracts.types import ExecutionStatus
from sqlbuild.executor.load.models import LoaderContext, LoadExecutionResult
from sqlbuild.spec.contracts.models import SourceEntry
from tests.unit.src.sqlbuild.executor.build._helpers._test_types import (
    ExternalBuildSourceLoadTestCase,
)
from tests.unit.src.sqlbuild.executor.load.helpers import CountingLoaderContextTestAdapter


@pytest.mark.parametrize(
    "test_case",
    [
        ExternalBuildSourceLoadTestCase(
            description="runs external source before build connections",
            source_name="raw_orders",
            loader_name="external_orders_loader",
            expected_status=ExecutionStatus.SUCCESS,
            expected_completed_key_count=1,
            expected_lifecycle_message="external build loader ran",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_external_source_load_when_preloading_then_records_progress_and_no_connection(
    test_case: ExternalBuildSourceLoadTestCase,
) -> None:
    adapter: CountingLoaderContextTestAdapter = CountingLoaderContextTestAdapter()
    key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SOURCE,
        name=test_case.source_name,
    )
    completed_results: list[object] = []
    started_nodes: list[tuple[str, object]] = []
    observed_connections: list[object] = []

    def external_loader(ctx: LoaderContext) -> None:
        observed_connections.append(ctx.connection)
        ctx.log(test_case.expected_lifecycle_message)
        return None

    results: ExternalSourceLoadResults = run_external_source_loads_before_connections(
        plan=PlanOutput(
            execution_order=(key,),
            selected_keys=frozenset({key}),
            source_load_entries=(
                SourceLoadPlanEntry(
                    key=key,
                    name=test_case.source_name,
                    loader=test_case.loader_name,
                    destination=test_case.source_name,
                ),
            ),
            source_map={
                test_case.source_name: SourceEntry(
                    name=test_case.source_name,
                    loader=test_case.loader_name,
                )
            },
        ),
        loader_functions=(
            DiscoveredLoaderFunction(
                file_path=Path("loaders/raw.py"),
                relative_path=Path("loaders/raw.py"),
                name=test_case.loader_name,
                function=external_loader,
                connection_mode=LoaderConnectionMode.EXTERNAL,
            ),
        ),
        adapter=adapter,
        connection_config={},
        runtime=BuildRuntimeParams(
            run_id="run-1",
            target="dev",
            effective_vars={},
        ),
        callbacks=BuildCallbacks(
            on_node_start=lambda name, *, resource_kind: started_nodes.append(
                (name, resource_kind)
            ),
            on_node_complete=completed_results.append,
        ),
    )

    assert adapter.connection_count == 0
    assert observed_connections == [None]
    assert len(results.completed_keys) == test_case.expected_completed_key_count
    assert tuple(result.status for result in results.results) == (test_case.expected_status,)
    assert isinstance(completed_results[0], LoadExecutionResult)
    assert started_nodes[0][0] == test_case.source_name
    assert results.results[0].lifecycle_events[0].content == test_case.expected_lifecycle_message
