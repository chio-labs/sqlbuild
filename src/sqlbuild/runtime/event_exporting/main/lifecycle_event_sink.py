"""Declare lifecycle-event sinks."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any, cast

from sqlbuild.python_nodes.main.attach_definition import attach_definition
from sqlbuild.runtime.event_exporting.constants import (
    EVENT_EXPORT_KINDS,
    EVENT_EXPORT_SEVERITIES,
    LIFECYCLE_EVENT_SINK_ATTRIBUTE,
)
from sqlbuild.runtime.event_exporting.exceptions import EventExporterInputError
from sqlbuild.runtime.event_exporting.models import LifecycleEventSinkDefinition
from sqlbuild.runtime.event_exporting.types import LifecycleEventKind
from sqlbuild.spec.contracts.types import EventExportSeverity


def lifecycle_event_sink(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
    event_kinds: Iterable[LifecycleEventKind | str] | None = None,
    min_severity: str = "debug",
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a synchronous function as a canonical lifecycle-event sink."""

    def decorate(inner: Callable[..., object]) -> Callable[..., object]:
        resolved_name: str = _sink_name(function=inner, explicit_name=name)
        resolved_kinds: frozenset[str] = _event_kinds(event_kinds)
        try:
            resolved_min_severity: EventExportSeverity = EventExportSeverity(min_severity)
        except ValueError as error:
            raise EventExporterInputError(
                "lifecycle-event sink min_severity must be one of: "
                + ", ".join(EVENT_EXPORT_SEVERITIES)
            ) from error
        return attach_definition(
            function=inner,
            attribute_name=LIFECYCLE_EVENT_SINK_ATTRIBUTE,
            definition=LifecycleEventSinkDefinition(
                name=resolved_name,
                event_kinds=resolved_kinds,
                min_severity=resolved_min_severity,
            ),
        )

    return decorate(function) if function is not None else decorate


def _sink_name(*, function: Callable[..., object], explicit_name: str | None) -> str:
    inner_function: Any = cast(Any, function)
    resolved_name: str = explicit_name or inner_function.__name__
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", resolved_name):
        raise EventExporterInputError("sink names must be lower snake_case Python identifiers")
    return resolved_name


def _event_kinds(values: Iterable[LifecycleEventKind | str] | None) -> frozenset[str]:
    try:
        resolved: frozenset[str] = (
            EVENT_EXPORT_KINDS
            if values is None
            else frozenset(LifecycleEventKind(value).value for value in values)
        )
    except (TypeError, ValueError) as error:
        raise EventExporterInputError(
            "lifecycle-event sink event_kinds must contain only strings"
        ) from error
    if not resolved:
        raise EventExporterInputError(
            "lifecycle-event sink event_kinds must be a non-empty subset of: "
            + ", ".join(sorted(EVENT_EXPORT_KINDS))
        )
    return resolved
