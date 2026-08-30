"""Resolved verbose build-start context output."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.commands.constants import (
    C0_CONTROL_CODE_LIMIT,
    C1_CONTROL_CODE_LIMIT,
    C1_CONTROL_CODE_START,
)
from sqlbuild.cli.commands.models import BuildRunContext
from sqlbuild.presentation.classes.cli_document import CliDocument
from sqlbuild.presentation.classes.cli_style import CliStyle


def write_build_run_context(*, stream: TextIO, context: BuildRunContext, use_color: bool) -> None:
    """Write resolved non-secret build placement, mode, and selection context."""

    stream.write(_format_build_run_context(context=context, use_color=use_color))
    stream.flush()


def _format_build_run_context(*, context: BuildRunContext, use_color: bool) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    document: CliDocument = CliDocument(style)
    selected_count: int = (
        len(context.plan.model_entries)
        + len(context.plan.seed_entries)
        + len(context.plan.function_entries)
        + len(context.plan.source_load_entries)
        + len(context.python_plan_entries)
    )
    total_source_load_count: int = sum(
        source.source_entry.loader is not None for source in context.project.sources
    )
    total_count: int = (
        len(context.project.models)
        + len(context.project.seeds)
        + len(context.project.functions)
        + total_source_load_count
        + len(context.discovered_inputs.task_functions)
        + len(context.discovered_inputs.asset_functions)
    )
    placement_rows: tuple[tuple[str, str], ...]
    if context.virtual_logical_schema is not None or context.virtual_physical_schema is not None:
        placement_rows = (
            ("logical schema", _display_value(context.virtual_logical_schema)),
            ("physical schema", _display_value(context.virtual_physical_schema)),
        )
    else:
        placement_rows = (("schema", _display_value(context.project.effective_target_schema)),)
    document.header(text="Execution")
    document.fields(
        rows=(
            ("command", _display_value(context.command)),
            ("run_id", _display_value(context.project.run_id)),
            ("target", _display_value(context.project.effective_target_name)),
            ("database", _display_value(context.project.effective_target_database)),
            *placement_rows,
            ("warehouse", _display_value(context.connection_config.get("warehouse"))),
            ("concurrency", f"{context.concurrency} configured limit"),
            ("full_refresh", str(context.full_refresh).lower()),
            ("selected", f"{selected_count:,} of {total_count:,} build resources"),
            ("date vars", _date_vars_display(context.project.effective_vars)),
        ),
        label_width=12,
    )
    if context.selector_files:
        document.blank()
        document.header(text="Selection files")
        for selector_file in context.selector_files:
            selector_noun: str = "selector" if selector_file.selector_count == 1 else "selectors"
            document.fields(
                rows=(
                    (
                        "selector_file",
                        f"{_safe_path(selector_file.path)} "
                        f"({selector_file.selector_count:,} {selector_noun})",
                    ),
                ),
                label_width=12,
            )
    document.blank()
    return document.render()


def _display_value(value: object) -> str:
    display_value: str | None = _safe_display_value(value)
    return display_value if display_value is not None else "not set"


def _safe_display_value(value: object) -> str | None:
    if isinstance(value, str | int | float) and not isinstance(value, bool):
        return _sanitize(str(value))
    return None


def _safe_path(path: Path) -> str:
    return _sanitize(str(path))


def _sanitize(value: str) -> str:
    return "".join(
        f"\\x{ord(character):02x}"
        if ord(character) < C0_CONTROL_CODE_LIMIT
        or C1_CONTROL_CODE_START <= ord(character) < C1_CONTROL_CODE_LIMIT
        else character
        for character in value
    )


def _validated_iso_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return None
    return _sanitize(value)


def _date_vars_display(effective_vars: dict[str, object]) -> str:
    start_date: str | None = _validated_iso_value(effective_vars.get("start_date"))
    end_date: str | None = _validated_iso_value(effective_vars.get("end_date"))
    if start_date is None and end_date is None:
        return "not set"
    if start_date is None:
        return f"end_date={end_date}"
    if end_date is None:
        return f"start_date={start_date}"
    return f"{start_date} to {end_date}"
