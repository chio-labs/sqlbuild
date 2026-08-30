"""Resolved verbose build-start context output."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.cli.commands.models import SelectorFileSummary
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.presentation.classes.cli_document import CliDocument
from sqlbuild.presentation.classes.cli_style import CliStyle


def write_build_run_context(
    *,
    stream: TextIO,
    command: str,
    project: CompiledProject,
    plan: PlanOutput,
    connection_config: dict[str, object],
    concurrency: int,
    full_refresh: bool,
    selector_files: tuple[SelectorFileSummary, ...],
    use_color: bool,
) -> None:
    """Write resolved non-secret build placement, mode, and selection context."""

    stream.write(
        _format_build_run_context(
            command=command,
            project=project,
            plan=plan,
            connection_config=connection_config,
            concurrency=concurrency,
            full_refresh=full_refresh,
            selector_files=selector_files,
            use_color=use_color,
        )
    )
    stream.flush()


def _format_build_run_context(
    *,
    command: str,
    project: CompiledProject,
    plan: PlanOutput,
    connection_config: dict[str, object],
    concurrency: int,
    full_refresh: bool,
    selector_files: tuple[SelectorFileSummary, ...],
    use_color: bool,
) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    document: CliDocument = CliDocument(style)
    selected_count: int = (
        len(plan.model_entries) + len(plan.seed_entries) + len(plan.function_entries)
    )
    total_count: int = len(project.models) + len(project.seeds) + len(project.functions)
    document.header(text="Execution")
    document.fields(
        rows=(
            ("command", command),
            ("run_id", project.run_id),
            ("target", _display_value(project.effective_target_name)),
            ("database", _display_value(project.effective_target_database)),
            ("schema", _display_value(project.effective_target_schema)),
            ("warehouse", _display_value(connection_config.get("warehouse"))),
            ("concurrency", f"{concurrency} configured limit"),
            ("full_refresh", str(full_refresh).lower()),
            ("selected", f"{selected_count:,} of {total_count:,} managed resources"),
            ("date vars", _date_vars_display(project.effective_vars)),
        ),
        label_width=12,
    )
    if selector_files:
        document.blank()
        document.header(text="Selection files")
        for selector_file in selector_files:
            selector_noun: str = "selector" if selector_file.selector_count == 1 else "selectors"
            document.fields(
                rows=(
                    (
                        "selector_file",
                        f"{selector_file.path} ({selector_file.selector_count:,} {selector_noun})",
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
        return str(value)
    return None


def _date_vars_display(effective_vars: dict[str, object]) -> str:
    start_date: str | None = _safe_display_value(effective_vars.get("start_date"))
    end_date: str | None = _safe_display_value(effective_vars.get("end_date"))
    if start_date is None and end_date is None:
        return "not set"
    if start_date is None:
        return f"end_date={end_date}"
    if end_date is None:
        return f"start_date={start_date}"
    return f"{start_date} to {end_date}"
