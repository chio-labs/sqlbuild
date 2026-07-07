"""Tests for source loader execution contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.executor.load.main.execute import execute_source_load
from sqlbuild.executor.load.models import (
    LoaderContext,
    LoadExecutionResult,
    LoadRuntimeParams,
)
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.provider.classes.container import ProviderContainer
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.executor.load._test_types import (
    SourceLoadExecutionContextTestCase,
    SourceLoadNoneReturnTestCase,
)
from tests.unit.src.sqlbuild.executor.load.helpers import LoaderContextTestAdapter
from tests.unit.src.sqlbuild.executor.python_nodes.helpers.helpers import ExecutionSlackProvider


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoadExecutionContextTestCase(
            description="passes runtime metadata and cursor fields to loader context",
            source_name="raw_orders",
            loader_name="raw_orders_loader",
            target_table="orders",
            database="analytics",
            schema="raw",
            run_id="run-123",
            target="dev",
            vars={"batch": 7},
            is_reload=True,
            start_cursor_ts=datetime(2026, 5, 1, tzinfo=UTC),
            end_cursor_ts=datetime(2026, 5, 2, tzinfo=UTC),
            start_cursor_int=10,
            end_cursor_int=20,
            expected_target="analytics.raw.orders",
            expected_current_cursor_value="max-value",
            expected_status=ExecutionStatus.SUCCESS,
            expected_rows_loaded=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_source_loader_when_executing_then_context_includes_runtime_metadata(
    test_case: SourceLoadExecutionContextTestCase,
) -> None:
    observed_contexts: list[LoaderContext] = []

    def raw_orders_loader(ctx: LoaderContext) -> None:
        observed_contexts.append(ctx)
        return None

    result: LoadExecutionResult = execute_source_load(
        source_entry=SourceEntry(
            name=test_case.source_name,
            database=test_case.database,
            schema=test_case.schema,
            table=test_case.target_table,
            loader=test_case.loader_name,
            cursor_column="updated_at",
        ),
        loader_function=DiscoveredLoaderFunction(
            file_path=Path("loaders/raw.py"),
            relative_path=Path("loaders/raw.py"),
            name=test_case.loader_name,
            function=raw_orders_loader,
        ),
        adapter=LoaderContextTestAdapter(),
        connection_config={"database": "loader.duckdb"},
        connection=object(),
        statement_recorder=StatementRecorder(),
        runtime=LoadRuntimeParams(
            run_id=test_case.run_id,
            target=test_case.target,
            vars=test_case.vars,
            is_reload=test_case.is_reload,
            start_cursor_ts=test_case.start_cursor_ts,
            end_cursor_ts=test_case.end_cursor_ts,
            start_cursor_int=test_case.start_cursor_int,
            end_cursor_int=test_case.end_cursor_int,
        ),
    )

    context: LoaderContext = observed_contexts[0]
    assert result.status == test_case.expected_status
    assert result.rows_loaded == test_case.expected_rows_loaded
    assert context.destination == test_case.expected_target
    assert context.destination_database == test_case.database
    assert context.destination_schema == test_case.schema
    assert context.destination_name == test_case.target_table
    assert context.run_id == test_case.run_id
    assert context.target == test_case.target
    assert context.vars == test_case.vars
    assert context.is_reload is test_case.is_reload
    assert context.start_cursor_ts == test_case.start_cursor_ts
    assert context.end_cursor_ts == test_case.end_cursor_ts
    assert context.start_cursor_int == test_case.start_cursor_int
    assert context.end_cursor_int == test_case.end_cursor_int
    assert context.current_cursor_value == test_case.expected_current_cursor_value


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoadExecutionContextTestCase(
            description="injects provider into source loader execution",
            source_name="raw_orders",
            loader_name="raw_orders_loader",
            target_table="orders",
            database=None,
            schema=None,
            run_id="run-123",
            target="dev",
            vars={},
            is_reload=False,
            start_cursor_ts=None,
            end_cursor_ts=None,
            start_cursor_int=None,
            end_cursor_int=None,
            expected_target="orders",
            expected_current_cursor_value=None,
            expected_status=ExecutionStatus.SUCCESS,
            expected_rows_loaded=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_provider_parameter_when_executing_source_loader_then_provider_is_injected(
    test_case: SourceLoadExecutionContextTestCase,
) -> None:
    observed_labels: list[str] = []

    def raw_orders_loader(
        ctx: LoaderContext,
        slack_provider: ExecutionSlackProvider,
    ) -> None:
        observed_labels.append(f"{ctx.target}:{slack_provider.label}")
        return None

    providers: ProviderContainer = ProviderSession(
        {"slack_provider": ExecutionSlackProvider(label="slack")}
    ).providers

    result: LoadExecutionResult = execute_source_load(
        source_entry=SourceEntry(
            name=test_case.source_name,
            table="__loader__raw_orders",
            loader=test_case.loader_name,
            meta={"sqlbuild_loader_node": True},
        ),
        loader_function=DiscoveredLoaderFunction(
            file_path=Path("loaders/raw.py"),
            relative_path=Path("loaders/raw.py"),
            name=test_case.loader_name,
            function=raw_orders_loader,
            destination="staging_raw_orders",
        ),
        adapter=LoaderContextTestAdapter(),
        connection_config={},
        connection=object(),
        statement_recorder=StatementRecorder(),
        runtime=LoadRuntimeParams(
            run_id=test_case.run_id,
            target=test_case.target,
            vars=test_case.vars,
            is_reload=test_case.is_reload,
            providers=providers,
        ),
    )

    assert result.status == test_case.expected_status
    assert result.rows_loaded == test_case.expected_rows_loaded
    assert tuple(observed_labels) == ("dev:slack",)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoadExecutionContextTestCase(
            description="exposes providers on source loader context",
            source_name="raw_orders",
            loader_name="raw_orders_loader",
            target_table="orders",
            database=None,
            schema=None,
            run_id="run-123",
            target="dev",
            vars={},
            is_reload=False,
            start_cursor_ts=None,
            end_cursor_ts=None,
            start_cursor_int=None,
            end_cursor_int=None,
            expected_target="orders",
            expected_current_cursor_value=None,
            expected_status=ExecutionStatus.SUCCESS,
            expected_rows_loaded=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_provider_container_when_executing_source_loader_then_context_exposes_providers(
    test_case: SourceLoadExecutionContextTestCase,
) -> None:
    observed_labels: list[str] = []

    def raw_orders_loader(ctx: LoaderContext) -> None:
        attr_provider: ExecutionSlackProvider = cast(
            ExecutionSlackProvider, ctx.providers.slack_provider
        )
        item_provider: ExecutionSlackProvider = cast(
            ExecutionSlackProvider, ctx.providers["slack_provider"]
        )
        observed_labels.append(f"{attr_provider.label}:{item_provider.label}")
        return None

    providers: ProviderContainer = ProviderSession(
        {"slack_provider": ExecutionSlackProvider(label="slack")}
    ).providers

    result: LoadExecutionResult = execute_source_load(
        source_entry=SourceEntry(
            name=test_case.source_name,
            table="__loader__raw_orders",
            loader=test_case.loader_name,
            meta={"sqlbuild_loader_node": True},
        ),
        loader_function=DiscoveredLoaderFunction(
            file_path=Path("loaders/raw.py"),
            relative_path=Path("loaders/raw.py"),
            name=test_case.loader_name,
            function=raw_orders_loader,
            destination="staging_raw_orders",
        ),
        adapter=LoaderContextTestAdapter(),
        connection_config={},
        connection=object(),
        statement_recorder=StatementRecorder(),
        runtime=LoadRuntimeParams(
            run_id=test_case.run_id,
            target=test_case.target,
            vars=test_case.vars,
            is_reload=test_case.is_reload,
            providers=providers,
        ),
    )

    assert result.status == test_case.expected_status
    assert result.rows_loaded == test_case.expected_rows_loaded
    assert tuple(observed_labels) == ("slack:slack",)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoadExecutionContextTestCase(
            description="normalizes missing provider container as source loader failure",
            source_name="raw_orders",
            loader_name="raw_orders_loader",
            target_table="orders",
            database=None,
            schema=None,
            run_id="run-123",
            target="dev",
            vars={},
            is_reload=False,
            start_cursor_ts=None,
            end_cursor_ts=None,
            start_cursor_int=None,
            end_cursor_int=None,
            expected_target="orders",
            expected_current_cursor_value=None,
            expected_status=ExecutionStatus.FAILED,
            expected_rows_loaded=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_provider_container_when_executing_source_loader_then_failure_is_recorded(
    test_case: SourceLoadExecutionContextTestCase,
) -> None:
    def raw_orders_loader(
        ctx: LoaderContext,
        slack_provider: ExecutionSlackProvider,
    ) -> None:
        del ctx, slack_provider
        return None

    result: LoadExecutionResult = execute_source_load(
        source_entry=SourceEntry(
            name=test_case.source_name,
            table="__loader__raw_orders",
            loader=test_case.loader_name,
            meta={"sqlbuild_loader_node": True},
        ),
        loader_function=DiscoveredLoaderFunction(
            file_path=Path("loaders/raw.py"),
            relative_path=Path("loaders/raw.py"),
            name=test_case.loader_name,
            function=raw_orders_loader,
            destination="staging_raw_orders",
        ),
        adapter=LoaderContextTestAdapter(),
        connection_config={},
        connection=object(),
        statement_recorder=StatementRecorder(),
        runtime=LoadRuntimeParams(
            run_id=test_case.run_id,
            target=test_case.target,
            vars=test_case.vars,
            is_reload=test_case.is_reload,
        ),
    )

    assert result.status == test_case.expected_status
    assert result.rows_loaded == test_case.expected_rows_loaded
    assert (
        "Provider parameter 'slack_provider' requires provider 'slack_provider', "
        "but no provider container is available"
    ) in (result.error_message or "")


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoadExecutionContextTestCase(
            description="injects provider into external source loader execution",
            source_name="raw_orders",
            loader_name="raw_orders_loader",
            target_table="orders",
            database="analytics",
            schema="raw",
            run_id="run-123",
            target="dev",
            vars={},
            is_reload=False,
            start_cursor_ts=None,
            end_cursor_ts=None,
            start_cursor_int=None,
            end_cursor_int=None,
            expected_target="analytics.raw.orders",
            expected_current_cursor_value=None,
            expected_status=ExecutionStatus.SUCCESS,
            expected_rows_loaded=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_provider_parameter_when_executing_external_source_loader_then_provider_is_injected(
    test_case: SourceLoadExecutionContextTestCase,
) -> None:
    observed_labels: list[str] = []

    def raw_orders_loader(
        ctx: LoaderContext,
        slack_provider: ExecutionSlackProvider,
    ) -> None:
        observed_labels.append(f"{ctx.connection}:{ctx.destination}:{slack_provider.label}")
        return None

    providers: ProviderContainer = ProviderSession(
        {"slack_provider": ExecutionSlackProvider(label="slack")}
    ).providers

    result: LoadExecutionResult = execute_source_load(
        source_entry=SourceEntry(
            name=test_case.source_name,
            database=test_case.database,
            schema=test_case.schema,
            table=test_case.target_table,
            loader=test_case.loader_name,
        ),
        loader_function=DiscoveredLoaderFunction(
            file_path=Path("loaders/raw.py"),
            relative_path=Path("loaders/raw.py"),
            name=test_case.loader_name,
            function=raw_orders_loader,
            connection_mode=LoaderConnectionMode.EXTERNAL,
        ),
        adapter=LoaderContextTestAdapter(),
        connection_config={},
        connection=object(),
        statement_recorder=StatementRecorder(),
        runtime=LoadRuntimeParams(
            run_id=test_case.run_id,
            target=test_case.target,
            vars=test_case.vars,
            is_reload=test_case.is_reload,
            providers=providers,
        ),
    )

    assert result.status == test_case.expected_status
    assert result.rows_loaded == test_case.expected_rows_loaded
    assert tuple(observed_labels) == ("None:analytics.raw.orders:slack",)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoadExecutionContextTestCase(
            description="exposes providers on external source loader context",
            source_name="raw_orders",
            loader_name="raw_orders_loader",
            target_table="orders",
            database="analytics",
            schema="raw",
            run_id="run-123",
            target="dev",
            vars={},
            is_reload=False,
            start_cursor_ts=None,
            end_cursor_ts=None,
            start_cursor_int=None,
            end_cursor_int=None,
            expected_target="analytics.raw.orders",
            expected_current_cursor_value=None,
            expected_status=ExecutionStatus.SUCCESS,
            expected_rows_loaded=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_provider_container_when_executing_external_loader_then_context_exposes_providers(
    test_case: SourceLoadExecutionContextTestCase,
) -> None:
    observed_labels: list[str] = []

    def raw_orders_loader(ctx: LoaderContext) -> None:
        attr_provider: ExecutionSlackProvider = cast(
            ExecutionSlackProvider, ctx.providers.slack_provider
        )
        item_provider: ExecutionSlackProvider = cast(
            ExecutionSlackProvider, ctx.providers["slack_provider"]
        )
        observed_labels.append(
            f"{ctx.connection}:{ctx.destination}:{attr_provider.label}:{item_provider.label}"
        )
        return None

    providers: ProviderContainer = ProviderSession(
        {"slack_provider": ExecutionSlackProvider(label="slack")}
    ).providers

    result: LoadExecutionResult = execute_source_load(
        source_entry=SourceEntry(
            name=test_case.source_name,
            database=test_case.database,
            schema=test_case.schema,
            table=test_case.target_table,
            loader=test_case.loader_name,
        ),
        loader_function=DiscoveredLoaderFunction(
            file_path=Path("loaders/raw.py"),
            relative_path=Path("loaders/raw.py"),
            name=test_case.loader_name,
            function=raw_orders_loader,
            connection_mode=LoaderConnectionMode.EXTERNAL,
        ),
        adapter=LoaderContextTestAdapter(),
        connection_config={},
        connection=object(),
        statement_recorder=StatementRecorder(),
        runtime=LoadRuntimeParams(
            run_id=test_case.run_id,
            target=test_case.target,
            vars=test_case.vars,
            is_reload=test_case.is_reload,
            providers=providers,
        ),
    )

    assert result.status == test_case.expected_status
    assert result.rows_loaded == test_case.expected_rows_loaded
    assert tuple(observed_labels) == ("None:analytics.raw.orders:slack:slack",)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoadNoneReturnTestCase(
            description="allows targeted self-managed intermediate loader to return none",
            source_name="fetch_orders",
            loader_name="fetch_orders",
            loader_target="staging_fetch_orders",
            expected_status=ExecutionStatus.SUCCESS,
            expected_rows_loaded=0,
        ),
        SourceLoadNoneReturnTestCase(
            description="fails untargeted self-managed intermediate loader returning none",
            source_name="fetch_orders",
            loader_name="fetch_orders",
            loader_target=None,
            expected_status=ExecutionStatus.FAILED,
            expected_rows_loaded=0,
            expected_error_fragment="returned no rows and has no destination declared",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_self_managed_intermediate_loader_when_returning_none_then_applies_target_rule(
    test_case: SourceLoadNoneReturnTestCase,
) -> None:
    def fetch_orders(ctx: LoaderContext) -> None:
        del ctx
        return None

    result: LoadExecutionResult = execute_source_load(
        source_entry=SourceEntry(
            name=test_case.source_name,
            table="__loader__fetch_orders",
            loader=test_case.loader_name,
            meta={"sqlbuild_loader_node": True},
        ),
        loader_function=DiscoveredLoaderFunction(
            file_path=Path("loaders/raw.py"),
            relative_path=Path("loaders/raw.py"),
            name=test_case.loader_name,
            function=fetch_orders,
            destination=test_case.loader_target,
        ),
        adapter=LoaderContextTestAdapter(),
        connection_config={},
        connection=object(),
        statement_recorder=StatementRecorder(),
        runtime=LoadRuntimeParams(
            run_id="run-1",
            target=None,
            vars={},
            is_reload=False,
        ),
    )

    assert result.status == test_case.expected_status
    assert result.rows_loaded == test_case.expected_rows_loaded
    assert test_case.expected_error_fragment in (result.error_message or "")
