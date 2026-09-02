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
