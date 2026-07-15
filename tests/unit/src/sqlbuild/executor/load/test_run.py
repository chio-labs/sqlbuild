"""Tests for standalone source loader pipeline execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.executor.contracts.types import ExecutionStatus
from sqlbuild.executor.load.main.run import run_load_pipeline
from sqlbuild.executor.load.models import (
    LoadCallbacks,
    LoaderContext,
    LoadExecutionResult,
    LoadRuntimeParams,
)
from sqlbuild.spec.contracts.models import SourceEntry
from tests.unit.src.sqlbuild.executor.load._test_types import (
    ExternalLoadPipelineTestCase,
    LoadPipelineSkipFanInTestCase,
)
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
    ids=lambda case: case.description,
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
        runtime=LoadRuntimeParams(
            run_id="run-1",
            target=None,
            vars={},
            is_reload=False,
        ),
        callbacks=LoadCallbacks(
            on_load_complete=completed_results.append,
        ),
    )

    assert adapter.connection_count == test_case.expected_connection_count
    assert (observed_connections[0] is None) is test_case.expected_connection_is_none
    assert tuple(result.status for result in results) == (test_case.expected_status,)
    assert completed_results == list(results)
    assert results[0].lifecycle_events[0].content == test_case.expected_lifecycle_message


@pytest.mark.parametrize(
    "test_case",
    (
        LoadPipelineSkipFanInTestCase(
            description="runs downstream when soft-skipped loader branch has successful sibling",
            skip_mode=SkipMode.SOFT,
            expected_statuses=(
                ExecutionStatus.SKIPPED,
                ExecutionStatus.SUCCESS,
                ExecutionStatus.SKIPPED,
                ExecutionStatus.SUCCESS,
            ),
            expected_skip_modes=("soft", None, "soft", None),
            expected_skip_reasons=(
                "no new orders",
                None,
                "All upstream loaders were soft-skipped",
                None,
            ),
        ),
        LoadPipelineSkipFanInTestCase(
            description="skips downstream when hard-skipped loader branch has successful sibling",
            skip_mode=SkipMode.HARD,
            expected_statuses=(
                ExecutionStatus.SKIPPED,
                ExecutionStatus.SUCCESS,
                ExecutionStatus.SKIPPED,
                ExecutionStatus.SKIPPED,
            ),
            expected_skip_modes=("hard", None, "hard", "hard"),
            expected_skip_reasons=(
                "no new orders",
                None,
                "Upstream loader hard-skipped",
                "Upstream loader hard-skipped",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_mixed_loader_skips_when_running_pipeline_then_fan_in_matches_mode(
    test_case: LoadPipelineSkipFanInTestCase,
) -> None:
    adapter: CountingLoaderContextTestAdapter = CountingLoaderContextTestAdapter()

    def a_loader(ctx: LoaderContext) -> object:
        return ctx.skip(reason="no new orders", mode=test_case.skip_mode)

    def x_loader(_ctx: LoaderContext) -> None:
        return None

    def b_loader(_ctx: LoaderContext) -> None:
        return None

    def c_loader(_ctx: LoaderContext) -> None:
        return None

    results: tuple[LoadExecutionResult, ...] = run_load_pipeline(
        sources=(
            SourceEntry(name="a", loader="a_loader"),
            SourceEntry(name="x", loader="x_loader"),
            SourceEntry(name="b", loader="b_loader"),
            SourceEntry(name="c", loader="c_loader"),
        ),
        loader_functions=(
            DiscoveredLoaderFunction(
                file_path=Path("loaders/a.py"),
                relative_path=Path("loaders/a.py"),
                name="a_loader",
                function=a_loader,
            ),
            DiscoveredLoaderFunction(
                file_path=Path("loaders/x.py"),
                relative_path=Path("loaders/x.py"),
                name="x_loader",
                function=x_loader,
            ),
            DiscoveredLoaderFunction(
                file_path=Path("loaders/b.py"),
                relative_path=Path("loaders/b.py"),
                name="b_loader",
                function=b_loader,
                depends_on=(a_loader,),
            ),
            DiscoveredLoaderFunction(
                file_path=Path("loaders/c.py"),
                relative_path=Path("loaders/c.py"),
                name="c_loader",
                function=c_loader,
                depends_on=(b_loader, x_loader),
            ),
        ),
        connection_config={},
        adapter=adapter,
        runtime=LoadRuntimeParams(
            run_id="run-1",
            target=None,
            vars={},
            is_reload=False,
        ),
    )

    assert tuple(result.source_name for result in results) == ("a", "x", "b", "c")
    assert tuple(result.status for result in results) == test_case.expected_statuses
    assert (
        tuple(getattr(result.skip_mode, "value", None) for result in results)
        == test_case.expected_skip_modes
    )
    assert tuple(result.skip_reason for result in results) == test_case.expected_skip_reasons
