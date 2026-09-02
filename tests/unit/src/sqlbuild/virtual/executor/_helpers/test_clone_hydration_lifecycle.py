from __future__ import annotations

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.observability import EventDispatcher, LifecycleEvent, dispatcher_scope
from sqlbuild.virtual.executor._helpers.clone import hydrate_and_register_relation
from tests.unit.src.sqlbuild.virtual.executor._helpers._test_types import (
    HydrationLifecycleTestCase,
)
from tests.unit.src.sqlbuild.virtual.executor._helpers.helpers import build_relation_location


@pytest.mark.parametrize(
    "test_case",
    (
        HydrationLifecycleTestCase(
            "model registration failure",
            "model",
            "orders",
            None,
            (
                "resource_attempt_started",
                "operation_started",
                "operation_completed",
                "resource_attempt_failed",
            ),
        ),
        HydrationLifecycleTestCase(
            "seed registration failure",
            "seed",
            "countries",
            None,
            (
                "resource_attempt_started",
                "operation_started",
                "operation_completed",
                "resource_attempt_failed",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_fresh_hydration_when_registration_fails_then_resource_attempt_fails(
    monkeypatch: pytest.MonkeyPatch,
    test_case: HydrationLifecycleTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    monkeypatch.setattr(adapter, "relation_exists", lambda **_: False)
    monkeypatch.setattr(adapter, "list_relations", lambda **_: ())
    monkeypatch.setattr(adapter, "ensure_schema", lambda **_: None)
    monkeypatch.setattr(adapter, "durable_clone", lambda **_: None)
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    def fail_registration() -> None:
        raise RuntimeError("state registration failed")

    with dispatcher_scope(dispatcher):
        with pytest.raises(RuntimeError, match="state registration failed"):
            hydrate_and_register_relation(
                adapter=adapter,
                destination_connection=object(),
                origin_location=build_relation_location(
                    schema="prod", name=test_case.resource_name
                ),
                destination_location=build_relation_location(
                    schema="dev", name=test_case.resource_name
                ),
                resource_kind=test_case.resource_kind,
                resource_name=test_case.resource_name,
                run_id="clone-run",
                register=fail_registration,
            )

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert tuple(event.run_id for event in events) == ("clone-run",) * len(events)
    assert events[-1].payload["error_type"] == "RuntimeError"


@pytest.mark.parametrize(
    "test_case",
    (HydrationLifecycleTestCase("reused model", "model", "orders", "reused", ()),),
    ids=lambda case: case.description,
)
def test_given_reused_hydration_when_registered_then_no_resource_attempt_is_fabricated(
    monkeypatch: pytest.MonkeyPatch,
    test_case: HydrationLifecycleTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    monkeypatch.setattr(adapter, "relation_exists", lambda **_: True)
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    registrations: list[str] = []

    with dispatcher_scope(dispatcher):
        action: str = hydrate_and_register_relation(
            adapter=adapter,
            destination_connection=object(),
            origin_location=build_relation_location(schema="prod", name=test_case.resource_name),
            destination_location=build_relation_location(
                schema="dev", name=test_case.resource_name
            ),
            resource_kind=test_case.resource_kind,
            resource_name=test_case.resource_name,
            run_id="clone-run",
            register=lambda: registrations.append(test_case.resource_name),
        )

    assert action == test_case.expected_action
    assert registrations == [test_case.resource_name]
    assert tuple(event.event_type for event in events) == test_case.expected_event_types
