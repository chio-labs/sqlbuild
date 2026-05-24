"""Tests for standalone source loader pipeline execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.executor.load.main.run import run_load_pipeline
from sqlbuild.executor.load.models import LoaderContext, LoadExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.executor.load._test_types import ExternalLoadPipelineTestCase
from tests.unit.src.sqlbuild.executor.load.helpers import CountingLoaderContextTestAdapter


@pytest.mark.parametrize(
    "test_case",
    [
        ExternalLoadPipelineTestCase(
            description="runs external loader without opening SQLBuild connection",
            source_name="raw_orders",
            loader_name="external_orders_loader",
            expected_connection_count=0,
            expected_connection_is_none=True,
            expected_status=ExecutionStatus.SUCCESS,
            expected_lifecycle_message="external loader ran",
        )
    ],
    ids=["runs external loader without opening SQLBuild connection"],
)
def test_given_external_loader_when_running_load_pipeline_then_does_not_open_connection(
    test_case: ExternalLoadPipelineTestCase,
) -> None:
    adapter: CountingLoaderContextTestAdapter = CountingLoaderContextTestAdapter()
    observed_connections: list[object] = []
    completed_results: list[LoadExecutionResult] = []

    def external_loader(ctx: LoaderContext) -> None:
        observed_connections.append(ctx.connection)
        ctx.log(test_case.expected_lifecycle_message)
        return None

    results: tuple[LoadExecutionResult, ...] = run_load_pipeline(
        sources=(
            SourceEntry(
                name=test_case.source_name,
                loader=test_case.loader_name,
            ),
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
        connection_config={},
        adapter=adapter,
        run_id="run-1",
        environment=None,
        vars={},
        is_reload=False,
        on_load_complete=completed_results.append,
    )

    assert adapter.connection_count == test_case.expected_connection_count
    assert (observed_connections[0] is None) is test_case.expected_connection_is_none
    assert tuple(result.status for result in results) == (test_case.expected_status,)
    assert completed_results == list(results)
    assert results[0].lifecycle_events[0].content == test_case.expected_lifecycle_message
