"""Recall replacement sinks: sinks that take a ``RecallWriter`` and decide what Recall stores."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import get_type_hints

from sqlbuild._native import (
    DiscoveredCommandOutputSink,
    DiscoveredEventExporter,
    EventExporterDiscoveryError,
    RecallWriter,
)


def _writer_parameters(function: Callable[..., object]) -> tuple[str, ...]:
    try:
        type_hints: dict[str, object] = get_type_hints(function)
    except (NameError, TypeError):
        type_hints = {}
    return tuple(
        name
        for name, parameter in inspect.signature(function).parameters.items()
        if type_hints.get(name, parameter.annotation) is RecallWriter
    )


def _location(sink: DiscoveredEventExporter | DiscoveredCommandOutputSink) -> str:
    return f"{sink.relative_path}:{getattr(sink.function, '__name__', sink.name)}"


def _writer_parameter(sink: DiscoveredEventExporter | DiscoveredCommandOutputSink) -> str | None:
    writers: tuple[str, ...] = _writer_parameters(sink.function)
    if not writers:
        return None
    if len(writers) > 1:
        raise EventExporterDiscoveryError(
            f"Recall replacement sink {_location(sink)} declares more than one RecallWriter "
            f"parameter: {', '.join(writers)}"
        )
    if sink.provider_usages:
        raise EventExporterDiscoveryError(
            f"Recall replacement sink {_location(sink)} must not declare provider parameters"
        )
    return writers[0]


def split_recall_sinks[SinkT: (DiscoveredEventExporter, DiscoveredCommandOutputSink)](
    *, sinks: tuple[SinkT, ...], history: str
) -> tuple[tuple[SinkT, str] | None, tuple[SinkT, ...]]:
    """The sink replacing Recall's ``history`` and its writer parameter, then the other sinks."""

    replacements: list[tuple[SinkT, str]] = []
    ordinary: list[SinkT] = []
    for sink in sinks:
        writer: str | None = _writer_parameter(sink)
        if writer is None:
            ordinary.append(sink)
        else:
            replacements.append((sink, writer))
    if len(replacements) > 1:
        raise EventExporterDiscoveryError(
            f"Only one sink may replace Recall {history} history; found "
            + ", ".join(_location(sink) for sink, _ in replacements)
        )
    return (replacements[0] if replacements else None), tuple(ordinary)
