"""Public decorator API for canonical lifecycle event exporters."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, cast

from sqlbuild.observability import LifecycleEvent
from sqlbuild.python_nodes._helpers.attachment import attach_definition, read_attached_definition
from sqlbuild.runtime.event_exporting.exceptions import EventExporterInputError
from sqlbuild.runtime.event_exporting.models import EventExporterDefinition

__all__ = (
    "EventExporterDefinition",
    "LifecycleEvent",
    "event_exporter",
    "get_event_exporter_definition",
)

_ATTRIBUTE_NAME: str = "__sqlbuild_event_exporter__"


def event_exporter(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a synchronous function as a SQLBuild lifecycle event exporter."""

    def decorate(inner: Callable[..., object]) -> Callable[..., object]:
        inner_function: Any = cast(Any, inner)
        resolved_name: str = name or inner_function.__name__
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", resolved_name):
            raise EventExporterInputError(
                "event exporter names must be lower snake_case Python identifiers"
            )
        return attach_definition(
            function=inner,
            attribute_name=_ATTRIBUTE_NAME,
            definition=EventExporterDefinition(name=resolved_name),
        )

    return decorate(function) if function is not None else decorate


def get_event_exporter_definition(
    function: Callable[..., object],
) -> EventExporterDefinition | None:
    """Return SQLBuild exporter metadata from a decorated function, if present."""

    return read_attached_definition(
        function=function,
        attribute_name=_ATTRIBUTE_NAME,
        definition_type=EventExporterDefinition,
    )
