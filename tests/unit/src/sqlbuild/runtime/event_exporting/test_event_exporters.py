from collections.abc import Callable
from typing import cast

import pytest

from sqlbuild.event_exporters import (
    EventExporterDefinition,
    event_exporter,
    get_event_exporter_definition,
)
from sqlbuild.runtime.event_exporting.exceptions import EventExporterInputError
from tests.unit.src.sqlbuild.runtime.event_exporting._test_types import (
    EventExporterDecoratorTestCase,
    EventExporterFilterTestCase,
    InvalidEventExporterNameTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDecoratorTestCase("direct form", "publish"),),
    ids=lambda case: case.description,
)
def test_given_direct_decorator_when_reading_definition_then_uses_function_name(
    test_case: EventExporterDecoratorTestCase,
) -> None:
    @event_exporter
    def publish(event: object) -> None:
        del event

    definition: EventExporterDefinition | None = get_event_exporter_definition(
        cast(Callable[..., object], publish)
    )

    assert definition is not None
    assert definition.name == test_case.expected_name


@pytest.mark.parametrize(
    "test_case",
    (EventExporterDecoratorTestCase("configured form", "warehouse_events"),),
    ids=lambda case: case.description,
)
def test_given_configured_decorator_when_reading_definition_then_uses_declared_name(
    test_case: EventExporterDecoratorTestCase,
) -> None:
    @event_exporter(name="warehouse_events")
    def publish(event: object) -> None:
        del event

    definition: EventExporterDefinition | None = get_event_exporter_definition(
        cast(Callable[..., object], publish)
    )

    assert definition is not None
    assert definition.name == test_case.expected_name


@pytest.mark.parametrize(
    "test_case",
    (InvalidEventExporterNameTestCase("invalid punctuation", "Bad-Name", "lower snake_case"),),
    ids=lambda case: case.description,
)
def test_given_invalid_name_when_decorating_then_rejects_declaration(
    test_case: InvalidEventExporterNameTestCase,
) -> None:
    with pytest.raises(EventExporterInputError, match=test_case.expected_error):

        @event_exporter(name=test_case.name)
        def publish(event: object) -> None:
            del event


@pytest.mark.parametrize(
    "test_case",
    (
        EventExporterFilterTestCase(
            "valid frozen filters",
            {"run", "statement"},
            "info",
            expected_kinds=frozenset({"run", "statement"}),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_valid_declaration_filters_when_decorating_then_options_are_frozen(
    test_case: EventExporterFilterTestCase,
) -> None:
    @event_exporter(
        event_kinds=cast(set[str], test_case.event_kinds),
        min_severity=test_case.min_severity,
    )
    def publish(event: object) -> None:
        del event

    definition: EventExporterDefinition | None = get_event_exporter_definition(
        cast(Callable[..., object], publish)
    )

    assert definition is not None
    assert definition.event_kinds == test_case.expected_kinds
    assert definition.min_severity == test_case.min_severity


@pytest.mark.parametrize(
    "test_case",
    (
        EventExporterFilterTestCase("unknown kind", {"kafka"}, "info", "event_kinds"),
        EventExporterFilterTestCase("empty kinds", set(), "info", "event_kinds"),
        EventExporterFilterTestCase("unknown severity", {"run"}, "fatal", "min_severity"),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_declaration_filters_when_decorating_then_rejects(
    test_case: EventExporterFilterTestCase,
) -> None:
    with pytest.raises(EventExporterInputError, match=test_case.expected_error):

        @event_exporter(
            event_kinds=cast(set[str], test_case.event_kinds),
            min_severity=test_case.min_severity,
        )
        def publish(event: object) -> None:
            del event
