"""Public typed sink declarations for lifecycle events and command output."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, cast

from sqlbuild.observability import LifecycleEvent, lifecycle_event_to_json
from sqlbuild.python_nodes._helpers.attachment import attach_definition, read_attached_definition
from sqlbuild.runtime.event_exporting.constants import EVENT_EXPORT_KINDS, EVENT_EXPORT_SEVERITIES
from sqlbuild.runtime.event_exporting.exceptions import EventExporterInputError
from sqlbuild.runtime.event_exporting.models import LifecycleEventSinkDefinition
from sqlbuild.runtime.output_capture._helpers.scope import output_capture_context
from sqlbuild.runtime.output_capture.exceptions import CommandOutputValidationError
from sqlbuild.runtime.output_capture.main.command_output_from_json import command_output_from_json
from sqlbuild.runtime.output_capture.main.command_output_to_json import command_output_to_json
from sqlbuild.runtime.output_capture.models import (
    CommandOutputRecord,
    CommandOutputSinkDefinition,
)
from sqlbuild.runtime.output_capture.types import CommandOutputStream
from sqlbuild.spec.contracts.types import EventExportSeverity

__all__ = (
    "CommandOutputRecord",
    "CommandOutputSinkDefinition",
    "CommandOutputStream",
    "CommandOutputValidationError",
    "LifecycleEventSinkDefinition",
    "LifecycleEvent",
    "command_output_context",
    "command_output_from_json",
    "command_output_sink",
    "command_output_to_json",
    "get_command_output_sink_definition",
    "get_lifecycle_event_sink_definition",
    "lifecycle_event_sink",
    "lifecycle_event_to_json",
)

_COMMAND_OUTPUT_SINK_ATTRIBUTE: str = "__sqlbuild_command_output_sink__"
_LIFECYCLE_EVENT_SINK_ATTRIBUTE: str = "__sqlbuild_lifecycle_event_sink__"


def lifecycle_event_sink(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
    event_kinds: Iterable[str] | None = None,
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
            attribute_name=_LIFECYCLE_EVENT_SINK_ATTRIBUTE,
            definition=LifecycleEventSinkDefinition(
                name=resolved_name,
                event_kinds=resolved_kinds,
                min_severity=resolved_min_severity,
            ),
        )

    return decorate(function) if function is not None else decorate


def command_output_sink(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
    streams: Iterable[CommandOutputStream | str] | None = None,
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a synchronous function as an explicit command-output sink."""

    def decorate(inner: Callable[..., object]) -> Callable[..., object]:
        resolved_name: str = _sink_name(function=inner, explicit_name=name)
        resolved_streams: frozenset[CommandOutputStream] = _command_output_streams(streams)
        return attach_definition(
            function=inner,
            attribute_name=_COMMAND_OUTPUT_SINK_ATTRIBUTE,
            definition=CommandOutputSinkDefinition(
                name=resolved_name,
                streams=resolved_streams,
            ),
        )

    return decorate(function) if function is not None else decorate


def get_lifecycle_event_sink_definition(
    function: Callable[..., object],
) -> LifecycleEventSinkDefinition | None:
    """Return lifecycle-event sink metadata attached to a function."""

    return read_attached_definition(
        function=function,
        attribute_name=_LIFECYCLE_EVENT_SINK_ATTRIBUTE,
        definition_type=LifecycleEventSinkDefinition,
    )


def get_command_output_sink_definition(
    function: Callable[..., object],
) -> CommandOutputSinkDefinition | None:
    """Return command-output sink metadata attached to a function."""

    return read_attached_definition(
        function=function,
        attribute_name=_COMMAND_OUTPUT_SINK_ATTRIBUTE,
        definition_type=CommandOutputSinkDefinition,
    )


@contextmanager
def command_output_context(*, external_context: Mapping[str, object]) -> Iterator[None]:
    """Attach opaque integration context to command-output records."""

    with output_capture_context(external_context=external_context):
        yield


def _sink_name(*, function: Callable[..., object], explicit_name: str | None) -> str:
    inner_function: Any = cast(Any, function)
    resolved_name: str = explicit_name or inner_function.__name__
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", resolved_name):
        raise EventExporterInputError("sink names must be lower snake_case Python identifiers")
    return resolved_name


def _event_kinds(values: Iterable[str] | None) -> frozenset[str]:
    try:
        resolved: frozenset[str] = EVENT_EXPORT_KINDS if values is None else frozenset(values)
    except TypeError as error:
        raise EventExporterInputError(
            "lifecycle-event sink event_kinds must contain only strings"
        ) from error
    if not all(isinstance(kind, str) for kind in resolved):
        raise EventExporterInputError("lifecycle-event sink event_kinds must contain only strings")
    unknown: frozenset[str] = resolved - EVENT_EXPORT_KINDS
    if not resolved or unknown:
        raise EventExporterInputError(
            "lifecycle-event sink event_kinds must be a non-empty subset of: "
            + ", ".join(sorted(EVENT_EXPORT_KINDS))
        )
    return resolved


def _command_output_streams(
    values: Iterable[CommandOutputStream | str] | None,
) -> frozenset[CommandOutputStream]:
    if values is None:
        return frozenset(CommandOutputStream)
    try:
        resolved: frozenset[CommandOutputStream] = frozenset(
            CommandOutputStream(value) for value in values
        )
    except (TypeError, ValueError) as error:
        raise EventExporterInputError(
            "command-output sink streams must contain only stdout or stderr"
        ) from error
    if not resolved:
        raise EventExporterInputError(
            "command-output sink streams must contain at least one stream"
        )
    return resolved
