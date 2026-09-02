from pathlib import Path
from unittest.mock import Mock

import pytest

import sqlbuild.virtual.executor.main.promote as promote_module
from sqlbuild.observability import EventDispatcher, LifecycleEvent, dispatcher_scope
from sqlbuild.virtual.executor.models import StateOperationHandle
from sqlbuild.virtual.state.types import StateOperationType
from tests.unit.src.sqlbuild.virtual.executor.main._test_types import (
    VirtualPromoteLifecycleTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        VirtualPromoteLifecycleTestCase(
            description="state backend connection fails after canonical start",
            expected_operation_id="promote-operation",
            expected_event_types=("operation_started", "operation_failed"),
            expected_state_result_calls=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_backend_connect_failure_when_promoting_then_handle_operation_fails(
    test_case: VirtualPromoteLifecycleTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    backend: Mock = Mock()
    backend.connect.side_effect = RuntimeError("state unavailable")
    state_result: Mock = Mock()
    monkeypatch.setattr(
        promote_module, "resolve_virtual_project_context", Mock(return_value=Mock())
    )
    monkeypatch.setattr(
        promote_module,
        "build_state_runtime",
        Mock(return_value=(Mock(connection=object(), schema="state"), backend)),
    )
    monkeypatch.setattr(
        promote_module,
        "create_state_operation_handle",
        Mock(
            return_value=StateOperationHandle(
                operation_id=test_case.expected_operation_id,
                operation_type=StateOperationType.PROMOTE,
            )
        ),
    )
    monkeypatch.setattr(promote_module, "write_state_operation_result", state_result)

    with dispatcher_scope(dispatcher), pytest.raises(RuntimeError, match="state unavailable"):
        promote_module.run_virtual_promote(
            project_dir=Path("."),
            discovered_inputs=Mock(),
            adapter=Mock(adapter_name="private-adapter"),
            connection_config={},
            from_virtual_environment_name="source",
            to_virtual_environment_name="target",
            options=Mock(),
            hooks=Mock(on_progress=None),
        )

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert events[0].operation_id == test_case.expected_operation_id
    assert events[-1].operation_id == test_case.expected_operation_id
    assert events[-1].payload["adapter"] == "custom"
    assert state_result.call_count == test_case.expected_state_result_calls


@pytest.mark.parametrize(
    "test_case",
    (
        VirtualPromoteLifecycleTestCase(
            description="state startup write failure does not attempt failed state write",
            expected_operation_id="promote-operation",
            expected_event_types=("operation_started", "operation_failed"),
            expected_state_result_calls=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_startup_state_write_failure_when_promoting_then_cleanup_canonical_failure_only(
    test_case: VirtualPromoteLifecycleTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    backend: Mock = Mock()
    state_result: Mock = Mock()
    startup_write: Mock = Mock(side_effect=RuntimeError("state start failed"))
    monkeypatch.setattr(
        promote_module, "resolve_virtual_project_context", Mock(return_value=Mock())
    )
    monkeypatch.setattr(
        promote_module,
        "build_state_runtime",
        Mock(return_value=(Mock(connection=object(), schema="state"), backend)),
    )
    monkeypatch.setattr(
        promote_module,
        "create_state_operation_handle",
        Mock(
            return_value=StateOperationHandle(
                operation_id=test_case.expected_operation_id,
                operation_type=StateOperationType.PROMOTE,
            )
        ),
    )
    monkeypatch.setattr(promote_module, "write_state_operation_started", startup_write)
    monkeypatch.setattr(promote_module, "write_state_operation_result", state_result)

    with dispatcher_scope(dispatcher), pytest.raises(RuntimeError, match="state start failed"):
        promote_module.run_virtual_promote(
            project_dir=Path("."),
            discovered_inputs=Mock(),
            adapter=Mock(adapter_name="duckdb"),
            connection_config={},
            from_virtual_environment_name="source",
            to_virtual_environment_name="target",
            options=Mock(),
            hooks=Mock(on_progress=None),
        )

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert events[-1].operation_id == test_case.expected_operation_id
    assert startup_write.call_count == 1
    assert state_result.call_count == test_case.expected_state_result_calls
    backend.close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
