"""Source freshness command output formatting."""

from __future__ import annotations

import json

from sqlbuild.cli.commands.main.helpers.freshness.models import (
    FreshnessCommandResult,
    FreshnessSourceResult,
)
from sqlbuild.cli.commands.main.helpers.freshness.types import FreshnessSourceStatus


def format_freshness_text(result: FreshnessCommandResult) -> str:
    """Format source freshness observations for humans."""

    lines: list[str] = ["Source freshness", ""]
    observed: tuple[FreshnessSourceResult, ...] = tuple(
        source for source in result.sources if source.status == FreshnessSourceStatus.OBSERVED
    )
    unknown: tuple[FreshnessSourceResult, ...] = tuple(
        source for source in result.sources if source.status == FreshnessSourceStatus.UNKNOWN
    )
    errors: tuple[FreshnessSourceResult, ...] = tuple(
        source for source in result.sources if source.status == FreshnessSourceStatus.ERROR
    )
    changed: tuple[FreshnessSourceResult, ...] = tuple(
        source for source in result.sources if source.status == FreshnessSourceStatus.CHANGED
    )
    unchanged: tuple[FreshnessSourceResult, ...] = tuple(
        source for source in result.sources if source.status == FreshnessSourceStatus.UNCHANGED
    )
    tolerated: tuple[FreshnessSourceResult, ...] = tuple(
        source for source in result.sources if source.status == FreshnessSourceStatus.TOLERATED
    )
    _append_group(lines, title="Observed", sources=observed)
    _append_group(lines, title="Changed", sources=changed)
    _append_group(lines, title="Unchanged", sources=unchanged)
    _append_group(lines, title="Tolerated", sources=tolerated)
    _append_group(lines, title="Unknown", sources=unknown)
    _append_group(lines, title="Errors", sources=errors)
    lines.append(
        f"Summary: observed={result.observed_count} "
        f"changed={result.changed_count} unchanged={result.unchanged_count} "
        f"tolerated={result.tolerated_count} "
        f"unknown={result.unknown_count} errors={result.error_count}"
    )
    return "\n".join(lines) + "\n"


def format_freshness_json(result: FreshnessCommandResult) -> str:
    """Serialize source freshness observations as JSON."""

    return json.dumps(
        {
            "sources": [_source_payload(source) for source in result.sources],
            "summary": {
                "observed": result.observed_count,
                "changed": result.changed_count,
                "unchanged": result.unchanged_count,
                "tolerated": result.tolerated_count,
                "unknown": result.unknown_count,
                "errors": result.error_count,
            },
        },
        indent=2,
    )


def _append_group(
    lines: list[str], *, title: str, sources: tuple[FreshnessSourceResult, ...]
) -> None:
    if not sources:
        return
    lines.append(f"{title} ({len(sources)})")
    source: FreshnessSourceResult
    for source in sources:
        lines.append("  " + _format_source_line(source))
    lines.append("")


def _format_source_line(source: FreshnessSourceResult) -> str:
    if source.status == FreshnessSourceStatus.OBSERVED:
        parts: list[str] = [source.name]
        if source.value_kind is not None:
            parts.append(source.value_kind)
        if source.current_data_version is not None:
            parts.append(source.current_data_version)
        if source.strategy is not None:
            parts.append(source.strategy)
        if source.lag_tolerance is not None:
            parts.append(f"tolerance {source.lag_tolerance}")
        return "  ".join(parts)
    if source.status in {
        FreshnessSourceStatus.CHANGED,
        FreshnessSourceStatus.UNCHANGED,
        FreshnessSourceStatus.TOLERATED,
    }:
        parts = [source.name]
        if source.previous_data_version is not None:
            parts.append(f"previous {source.previous_data_version}")
        if source.current_data_version is not None:
            parts.append(f"current {source.current_data_version}")
        if source.lag_tolerance is not None:
            parts.append(f"tolerance {source.lag_tolerance}")
        return "  ".join(parts)
    if source.message is not None:
        return f"{source.name}  {source.message}"
    return source.name


def _source_payload(source: FreshnessSourceResult) -> dict[str, object]:
    return {
        "name": source.name,
        "status": source.status.value,
        "strategy": source.strategy,
        "value_kind": source.value_kind,
        "current_data_version": source.current_data_version,
        "previous_data_version": source.previous_data_version,
        "lag_tolerance": source.lag_tolerance,
        "target": {
            "database": source.target_database,
            "schema": source.target_schema,
            "name": source.target_name,
        },
        "message": source.message,
    }
