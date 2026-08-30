from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any, cast

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.clone.connections import (
    close_clone_targets,
    connect_clone_targets,
)
from sqlbuild.cli.commands.models import (
    CloneCommandRequest,
    CloneConnectionContext,
    CloneInvocation,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig
from tests.unit.src.sqlbuild.cli.commands._helpers.clone._test_types import (
    CloneConnectionLifecycleTestCase,
)


class _ConnectionTrackingAdapter:
    def __init__(self) -> None:
        self.connected_configs: list[dict[str, object]] = []
        self.closed_connections: list[object] = []
        self.connection: object = object()

    def connect(self, config: dict[str, Any]) -> object:
        self.connected_configs.append(config)
        return self.connection

    def close(self, connection: object) -> None:
        self.closed_connections.append(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        CloneConnectionLifecycleTestCase(
            description="connects and closes only the destination session",
            expected_destination_config={"database": "destination.duckdb"},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clone_targets_when_connecting_then_only_destination_session_is_opened_once(
    test_case: CloneConnectionLifecycleTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: _ConnectionTrackingAdapter = _ConnectionTrackingAdapter()
    monkeypatch.setattr(
        "sqlbuild.cli.commands._helpers.clone.connections.resolve_target_connection_config",
        lambda **_: test_case.expected_destination_config,
    )
    invocation: CloneInvocation = CloneInvocation(
        effective_project_dir=Path("."),
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(name="test", adapter="duckdb"),
            local_config=LocalConfig(),
        ),
        adapter_name="duckdb",
        adapter=cast(BaseAdapter, adapter),
        destination_target_name="dev",
        use_color=False,
        progress_stream=StringIO(),
    )
    request: CloneCommandRequest = CloneCommandRequest(
        project_dir=None,
        no_color=True,
        no_sql_validation=False,
        origin_target_name="prod",
        destination_target_name="dev",
        hard_copy=False,
    )

    context: CloneConnectionContext = connect_clone_targets(request=request, invocation=invocation)
    close_clone_targets(invocation=invocation, connection_context=context)

    assert adapter.connected_configs == [test_case.expected_destination_config]
    assert adapter.closed_connections == [adapter.connection]
