"""Clone command output helpers."""

from __future__ import annotations

from sqlbuild.cli.commands.main.shared.helpers.colors import colorize_status
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus


def render_clone_output(
    *,
    result: CloneExecutionResult,
    from_environment: str,
    to_environment: str,
    use_color: bool,
) -> None:
    print(f"sqb clone  from={from_environment} to={to_environment}\n")
    item: CloneItemResult
    for item in result.item_results:
        status_text: str = "OK"
        if item.status == CloneStatus.WARNING:
            status_text = "WARN"
        if item.status == CloneStatus.FAILED:
            status_text = "FAIL"
        rendered_status: str = colorize_status(status_text, use_color=use_color)
        print(f"  {item.name:<40} {rendered_status:<6} {item.action}")
        if item.message is not None:
            print(f"    {item.message}")
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
        print("Completed successfully.")
    else:
        print("Completed with warnings.")
    print(
        f"CLONED={cloned_count}  COPIED={copied_count}  RECREATED_VIEWS={recreated_count}  "
        f"PASS={success_count}  WARN={warning_count}  FAIL={fail_count}  "
        f"TOTAL={len(result.item_results)}"
    )


def is_clone_success(result: CloneExecutionResult) -> bool:
    return all(item.status == CloneStatus.SUCCESS for item in result.item_results)
