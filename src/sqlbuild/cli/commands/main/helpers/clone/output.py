"""Clone command output helpers."""

from __future__ import annotations

from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.shared.helpers.alignment import format_aligned_name_value, resolve_name_column_width
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.summary_footer import format_summary_footer


def render_clone_output(
    *,
    result: CloneExecutionResult,
    origin_target_name: str,
    destination_target_name: str,
    use_color: bool,
) -> None:
    style: CliStyle = CliStyle(use_color=use_color)
    print(
        f"{style.title('sqb clone')}  "
        f"{style.label('origin=')}{style.value(origin_target_name)} "
        f"{style.label('destination=')}{style.value(destination_target_name)}\n"
    )
    name_column_width: int = resolve_name_column_width(
        tuple(item.name for item in result.item_results)
    )
    item: CloneItemResult
    for item in result.item_results:
        status_text: str = "OK"
        if item.status == CloneStatus.WARNING:
            status_text = "WARN"
        if item.status == CloneStatus.FAILED:
            status_text = "FAIL"
        rendered_status: str = style.status(status_text)
        print(
            format_aligned_name_value(
                plain_name=item.name,
                styled_name=style.object_name(item.name),
                value=f"{rendered_status:<6} {style.accent(item.action.value)}",
                name_column_width=name_column_width,
            )
        )
        if item.message is not None:
            print(f"    {style.muted(item.message)}")
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
    if warning_count == 0 and fail_count == 0:
        print(style.success_strong("Completed successfully."))
    else:
        print(style.warning_strong("Completed with warnings."))
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
