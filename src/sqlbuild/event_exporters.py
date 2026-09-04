"""Public decorator API for canonical lifecycle event exporters."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any, cast

from sqlbuild.observability import LifecycleEvent
from sqlbuild.python_nodes._helpers.attachment import attach_definition, read_attached_definition
from sqlbuild.runtime.event_exporting.constants import EVENT_EXPORT_KINDS, EVENT_EXPORT_SEVERITIES
from sqlbuild.runtime.event_exporting.exceptions import EventExporterInputError
from sqlbuild.runtime.event_exporting.models import EventExporterDefinition
from sqlbuild.spec.contracts.types import EventExportSeverity

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
    event_kinds: Iterable[str] | None = None,
    min_severity: str = "debug",
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a synchronous function as a SQLBuild lifecycle event exporter."""

    def decorate(inner: Callable[..., object]) -> Callable[..., object]:
        inner_function: Any = cast(Any, inner)
        resolved_name: str = name or inner_function.__name__
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", resolved_name):
            raise EventExporterInputError(
                "event exporter names must be lower snake_case Python identifiers"
            )
        try:
            resolved_kinds: frozenset[str] = (
                EVENT_EXPORT_KINDS if event_kinds is None else frozenset(event_kinds)
            )
        except TypeError as error:
            raise EventExporterInputError(
                "event exporter event_kinds must contain only strings"
            ) from error
        if not all(isinstance(kind, str) for kind in resolved_kinds):
            raise EventExporterInputError("event exporter event_kinds must contain only strings")
        unknown_kinds: frozenset[str] = resolved_kinds - EVENT_EXPORT_KINDS
        if not resolved_kinds or unknown_kinds:
            raise EventExporterInputError(
                "event exporter event_kinds must be a non-empty subset of: "
                + ", ".join(sorted(EVENT_EXPORT_KINDS))
            )
        try:
            resolved_min_severity: EventExportSeverity = EventExportSeverity(min_severity)
        except ValueError as error:
            raise EventExporterInputError(
                "event exporter min_severity must be one of: " + ", ".join(EVENT_EXPORT_SEVERITIES)
            ) from error
        return attach_definition(
            function=inner,
            attribute_name=_ATTRIBUTE_NAME,
            definition=EventExporterDefinition(
                name=resolved_name,
                event_kinds=resolved_kinds,
                min_severity=resolved_min_severity,
            ),
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
