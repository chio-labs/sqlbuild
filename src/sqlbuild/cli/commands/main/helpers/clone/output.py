"""Clone command output helpers."""

from __future__ import annotations

from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.summary_footer import format_summary_footer


def render_clone_header(
    *, origin_target_name: str, destination_target_name: str, total: int, use_color: bool
) -> str:
    """Render the persistent clone header naming origin, destination, and relation count."""

    style: CliStyle = CliStyle(use_color=use_color)
    return (
        f"{style.title('sqb clone')}  "
        f"{style.label('origin=')}{style.value(origin_target_name)} "
        f"{style.label('destination=')}{style.value(destination_target_name)}  "
        f"{style.muted(f'({total} relation{"" if total == 1 else "s"})')}"
    )


def _clone_status_text(status: CloneStatus) -> str:
    if status == CloneStatus.WARNING:
        return "WARN"
    if status == CloneStatus.FAILED:
        return "FAIL"
    return "OK"


def render_clone_item_line(
    *, index: int, total: int, item: CloneItemResult, use_color: bool
) -> str:
    """Render one streamed clone line: position, action, origin to destination, and status."""

    style: CliStyle = CliStyle(use_color=use_color)
    position: str = f"{index:>{len(str(total))}}/{total}"
    relation_flow: str = item.name
    if item.origin_relation is not None and item.destination_relation is not None:
        relation_flow = (
            f"{style.object_name(item.origin_relation)} "
            f"{style.muted('->')} {style.object_name(item.destination_relation)}"
        )
    duration: str = (
        f"  {style.muted(f'{item.duration_seconds:.2f}s')}"
        if item.duration_seconds is not None
        else ""
    )
    return (
        f"  {style.muted(position)}  {style.accent(item.action.value):<18} "
        f"{relation_flow}  {style.status(_clone_status_text(item.status))}{duration}"
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
    print()
    elapsed: str = f" ({elapsed_seconds:.2f}s)" if elapsed_seconds is not None else ""
    if warning_count == 0 and fail_count == 0:
        print(style.success_strong(f"Completed successfully.{elapsed}"))
    else:
        print(style.warning_strong(f"Completed with warnings.{elapsed}"))
    print(
        format_summary_footer(
            counts=(
                ("CLONED", cloned_count),
                ("COPIED", copied_count),
                ("RECREATED_VIEWS", recreated_count),
                ("PASS", success_count),
                ("WARN", warning_count),
                ("FAIL", fail_count),
                ("TOTAL", len(result.item_results)),
            ),
            use_color=use_color,
        )
    )


def is_clone_success(result: CloneExecutionResult) -> bool:
    return all(item.status == CloneStatus.SUCCESS for item in result.item_results)
