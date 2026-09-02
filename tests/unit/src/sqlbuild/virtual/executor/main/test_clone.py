from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from sqlbuild.observability import EventDispatcher, LifecycleEvent, dispatcher_scope
from sqlbuild.virtual.executor.main import clone
from sqlbuild.virtual.executor.models import (
    CloneOptions,
    VirtualCloneItemResult,
    VirtualCloneResult,
)
from sqlbuild.virtual.state.types import PhysicalArtifactType
from tests.unit.src.sqlbuild.virtual.executor.main._test_types import (
    VirtualCloneAggregateTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        VirtualCloneAggregateTestCase(
            "missing artifact fails aggregate",
            "missing",
            "operation_failed",
            "clone_execution_failed",
        ),
        VirtualCloneAggregateTestCase(
            "skipped lock completes aggregate", "skipped_locked", "operation_completed", None
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_virtual_clone_result_when_api_returns_then_aggregate_uses_destination_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_case: VirtualCloneAggregateTestCase,
) -> None:
    adapter: Mock = Mock()
    destination_connection: object = object()
    state_connection: object = object()
    adapter.connect.return_value = destination_connection
    backend: Mock = Mock()
    backend.connect.return_value = state_connection
    config: Mock = Mock(schema="state", connection={})
    pipeline: Mock = Mock()
    pipeline.destination_project.run_id = "clone-run"
    versions: Mock = Mock(mode="workspace", origin_state_used=False)
    item: VirtualCloneItemResult = VirtualCloneItemResult(
        artifact_type=PhysicalArtifactType.MODEL,
        artifact_name="orders",
        version_hash="hash",
        action=test_case.action,
    )
    monkeypatch.setattr(clone, "build_state_runtime", lambda **_: (config, backend))
    monkeypatch.setattr(clone, "compile_clone_pipeline", lambda **_: pipeline)
    monkeypatch.setattr(clone, "build_clone_project_context", lambda _: Mock())
    monkeypatch.setattr(clone, "resolve_clone_versions", lambda **_: versions)
    monkeypatch.setattr(clone, "build_clone_origin_lookup", lambda **_: Mock())
    monkeypatch.setattr(clone, "hydrate_clone_model_relations", lambda **_: (item,))
    monkeypatch.setattr(clone, "hydrate_clone_seed_relations", lambda **_: ())
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    with dispatcher_scope(dispatcher):
        result: VirtualCloneResult = clone.run_virtual_clone(
            project_dir=tmp_path,
            discovered_inputs=Mock(),
            adapter=adapter,
            origin_target_name="prod",
            destination_target_name="dev",
            destination_connection_config={},
            options=CloneOptions(skip_locked=test_case.action == "skipped_locked"),
        )

    aggregate_events: tuple[LifecycleEvent, LifecycleEvent] = (events[4], events[-1])
    assert result.item_results == (item,)
    assert tuple(event.event_type for event in aggregate_events) == (
        "operation_started",
        test_case.expected_terminal,
    )
    assert tuple(event.run_id for event in aggregate_events) == ("clone-run", "clone-run")
    assert aggregate_events[-1].payload.get("error_code") == test_case.expected_error_code
