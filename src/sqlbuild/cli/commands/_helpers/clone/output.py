"""Clone command output helpers."""

from __future__ import annotations

import re

from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.completion_line import format_completion_line
from sqlbuild.presentation.main.summary_footer import format_summary_footer
from sqlbuild.presentation.types import CompletionState

_QUOTED_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(
    r'("(?:[^"]|"")*"|`(?:[^`]|``)*`|\[(?:[^\]]|\]\])*\])'
)


def render_clone_header(
    *, origin_target_name: str, destination_target_name: str, total: int, use_color: bool
) -> str:
    """Render the persistent clone header naming origin, destination, and resource count."""

    style: CliStyle = CliStyle(use_color=use_color)
    return (
        f"{style.title('sqb clone')}  "
        f"{style.label('origin=')}{style.value(origin_target_name)} "
        f"{style.label('destination=')}{style.value(destination_target_name)}  "
        f"{style.muted(f'({total} resource{"" if total == 1 else "s"})')}"
    )


def _clone_status_text(status: CloneStatus) -> str:
    if status == CloneStatus.WARNING:
        return "WARN"
    if status == CloneStatus.FAILED:
        return "FAIL"
    return "OK"


def clone_relation_flow_text(
    *, name: str, origin_relation: str | None, destination_relation: str | None
) -> str:
    """Return the normalized plain-text relation flow used for clone progress."""

    if origin_relation is None or destination_relation is None:
        return name.lower()
    return (
        f"{clone_relation_display_name(origin_relation)} -> "
        f"{clone_relation_display_name(destination_relation)}"
    )


def clone_relation_display_name(relation: str) -> str:
    """Normalize ordinary identifiers while preserving quoted identifier case."""

    parts: list[str] = _QUOTED_IDENTIFIER_PATTERN.split(relation)
    return "".join(
        part if _QUOTED_IDENTIFIER_PATTERN.fullmatch(part) else part.lower() for part in parts
    )


def render_clone_item_line(
    *,
    index: int,
    total: int,
    item: CloneItemResult,
    use_color: bool,
    relation_width: int | None = None,
) -> str:
    """Render one streamed clone line: position, action, origin to destination, and status."""

    style: CliStyle = CliStyle(use_color=use_color)
    position: str = f"{index:>{len(str(total))}}/{total}"
    plain_relation_flow: str = clone_relation_flow_text(
        name=item.name,
        origin_relation=item.origin_relation,
        destination_relation=item.destination_relation,
    )
    relation_flow: str = style.object_name(plain_relation_flow)
    if item.origin_relation is not None and item.destination_relation is not None:
        relation_flow = (
            f"{style.object_name(clone_relation_display_name(item.origin_relation))} "
            f"{style.muted('->')} "
            f"{style.object_name(clone_relation_display_name(item.destination_relation))}"
        )
    effective_relation_width: int = max(len(plain_relation_flow), relation_width or 0)
    relation_padding: str = " " * (effective_relation_width - len(plain_relation_flow))
    action: str = item.action.value
    action_width: int = max(len(value.value) for value in CloneAction)
    action_padding: str = " " * (action_width - len(action))
    duration: str = (
        f"  {style.muted(f'{item.duration_seconds:.2f}s')}"
        if item.duration_seconds is not None
        else ""
    )
    return (
        f"  {style.muted(position)}  {style.accent(action)}{action_padding}  "
        f"{relation_flow}{relation_padding}  "
        f"{style.status(status=_clone_status_text(status=item.status))}{duration}"
    )


def render_clone_output(
    *,
    result: CloneExecutionResult,
    elapsed_seconds: float | None = None,
    use_color: bool,
) -> None:
    style: CliStyle = CliStyle(use_color=use_color)
    item: CloneItemResult
    for item in result.item_results:
        if item.message is not None and item.status != CloneStatus.SUCCESS:
            print(f"  {style.object_name(item.name)}  {style.muted(item.message)}")
    success_count: int = sum(
        1 for item in result.item_results if item.status == CloneStatus.SUCCESS
    )
    warning_count: int = sum(
        1 for item in result.item_results if item.status == CloneStatus.WARNING
    )
    fail_count: int = sum(1 for item in result.item_results if item.status == CloneStatus.FAILED)
    cloned_count: int = sum(1 for item in result.item_results if item.action == CloneAction.CLONED)
    copied_count: int = sum(1 for item in result.item_results if item.action == CloneAction.COPIED)
    recreated_count: int = sum(
        1 for item in result.item_results if item.action == CloneAction.RECREATED_VIEW
    )
    recreated_function_count: int = sum(
        1 for item in result.item_results if item.action == CloneAction.RECREATED_FUNCTION
    )
    print()
    elapsed: str = f"({elapsed_seconds:.2f}s)" if elapsed_seconds is not None else ""
    counts_summary: str = format_summary_footer(
        counts=(
            ("CLONED", cloned_count),
            ("COPIED", copied_count),
            ("RECREATED_VIEWS", recreated_count),
            ("RECREATED_FUNCTIONS", recreated_function_count),
            ("PASS", success_count),
            ("WARN", warning_count),
            ("FAIL", fail_count),
            ("TOTAL", len(result.item_results)),
        ),
        use_color=use_color,
        elapsed=elapsed or None,
    )
    if warning_count == 0 and fail_count == 0:
        completion_state: CompletionState = CompletionState.OK
        completion_label: str = "Completed successfully"
    elif fail_count == 0:
        completion_state = CompletionState.WARN
        completion_label = "Completed with warnings"
    else:
        completion_state = CompletionState.FAIL
        completion_label = "Completed with errors"
    print(
        format_completion_line(
            style=style,
            state=completion_state,
            label=completion_label,
            summary=counts_summary,
        )
    )


def is_clone_success(result: CloneExecutionResult) -> bool:
    return all(item.status != CloneStatus.FAILED for item in result.item_results)
