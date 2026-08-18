"""Source freshness command output formatting."""

from __future__ import annotations

import json

from sqlbuild.cli.commands.models import (
    FreshnessCommandResult,
    FreshnessSourceResult,
)
from sqlbuild.cli.commands.types import FreshnessSourceStatus
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.summary_footer import format_summary_footer
from sqlbuild.presentation.main.tree_connector import tree_connector

_FRESHNESS_GROUPS: tuple[tuple[FreshnessSourceStatus, str], ...] = (
    (FreshnessSourceStatus.OBSERVED, "Observed"),
    (FreshnessSourceStatus.CHANGED, "Changed"),
    (FreshnessSourceStatus.UNCHANGED, "Unchanged"),
    (FreshnessSourceStatus.TOLERATED, "Tolerated"),
    (FreshnessSourceStatus.UNKNOWN, "Unknown"),
    (FreshnessSourceStatus.ERROR, "Errors"),
)


def format_freshness_text(*, result: FreshnessCommandResult, use_color: bool = False) -> str:
    """Format source freshness observations for humans."""

    style: CliStyle = CliStyle(use_color=use_color)
    lines: list[str] = [style.title("Source freshness")]
    name_width: int = max((len(source.name) for source in result.sources), default=0)
    status: FreshnessSourceStatus
    title: str
    for status, title in _FRESHNESS_GROUPS:
        sources: tuple[FreshnessSourceResult, ...] = tuple(
            source for source in result.sources if source.status == status
        )
        lines = _append_group(
            lines=lines,
            title=title,
            sources=sources,
            name_width=name_width,
            style=style,
        )
    lines.append("")
    lines.append(
        format_summary_footer(
            counts=(
                ("OBSERVED", result.observed_count),
                ("CHANGED", result.changed_count),
                ("UNCHANGED", result.unchanged_count),
                ("TOLERATED", result.tolerated_count),
                ("UNKNOWN", result.unknown_count),
                ("ERROR", result.error_count),
            ),
            use_color=use_color,
        )
    )
    if any(source.age_status is not None for source in result.sources):
        lines.append(
            f"{style.section('Age policy')}  "
            + format_summary_footer(
                counts=(
                    ("PASS", result.age_pass_count),
                    ("WARN", result.age_warn_count),
                    ("ERROR", result.age_error_count),
                    ("UNKNOWN", result.age_unknown_count),
                ),
                use_color=use_color,
            )
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
                "age_pass": result.age_pass_count,
                "age_warn": result.age_warn_count,
                "age_error": result.age_error_count,
                "age_unknown": result.age_unknown_count,
            },
        },
        indent=2,
    )


def _append_group(
    *,
    lines: list[str],
    title: str,
    sources: tuple[FreshnessSourceResult, ...],
    name_width: int,
    style: CliStyle,
) -> list[str]:
    if not sources:
        return lines
    lines.append("")
    lines.append(style.section(f"{title} ({len(sources)})"))
    source: FreshnessSourceResult
    for index, source in enumerate(sources):
        connector: str = tree_connector(style=style, last=index == len(sources) - 1)
        detail: str = _format_source_detail(source=source, style=style)
        suffix: str = f"  {detail}" if detail else ""
        lines.append(f"{connector} {style.object_name(f'{source.name:<{name_width}}')}{suffix}")
    return lines


def _format_source_detail(*, source: FreshnessSourceResult, style: CliStyle) -> str:
    if source.status == FreshnessSourceStatus.OBSERVED:
        parts: list[str] = []
        if source.current_data_version is not None:
            parts.append(style.muted(f"value {source.current_data_version}"))
        if source.value_kind is not None:
            parts.append(style.muted(f"kind {source.value_kind}"))
        if source.strategy is not None:
            parts.append(style.muted(f"via {source.strategy}"))
        if source.lag_tolerance is not None:
            parts.append(style.muted(f"tolerance {source.lag_tolerance}"))
        if source.age_status is not None:
            parts.append(
                style.status(
                    status=source.age_status.value,
                    text=f"age {source.age_status.value}",
                )
            )
        return "  ".join(parts)
    if source.status in {
        FreshnessSourceStatus.CHANGED,
        FreshnessSourceStatus.UNCHANGED,
        FreshnessSourceStatus.TOLERATED,
    }:
        parts = []
        if source.previous_data_version is not None:
            parts.append(style.muted(f"previous {source.previous_data_version}"))
        if source.current_data_version is not None:
            parts.append(style.muted(f"current {source.current_data_version}"))
        if source.lag_tolerance is not None:
            parts.append(style.muted(f"tolerance {source.lag_tolerance}"))
        if source.age_status is not None:
            parts.append(
                style.status(
                    status=source.age_status.value,
                    text=f"age {source.age_status.value}",
                )
            )
        return "  ".join(parts)
    if source.message is not None:
        if source.status == FreshnessSourceStatus.ERROR:
            return style.error(source.message)
        return style.warning(source.message)
    return ""


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
        "age_status": source.age_status.value if source.age_status is not None else None,
    }
