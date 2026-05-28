"""Reconcile command output helpers."""

from __future__ import annotations

from sqlbuild.shared.helpers.colors import blue_bold, dim, green, green_bold


def format_reconcile_output(*, message: str, use_color: bool) -> str:
    """Format virtual reconcile output."""

    title: str = green_bold("Virtual reconcile") if use_color else "Virtual reconcile"
    rendered_message: str = _format_reconcile_message(message=message, use_color=use_color)
    return "\n" + title + "\n\n" + rendered_message + "\n"


def _format_reconcile_message(*, message: str, use_color: bool) -> str:
    if not use_color:
        return message
    if "no issues" in message:
        return blue_bold(message)
    lines: list[str] = message.splitlines()
    if not lines or lines[0] not in {"Repair", "Attach"}:
        return message
    formatted: list[str] = [green(lines[0])]
    for line in lines[1:]:
        stripped: str = line.strip()
        label, _, value = stripped.partition("  ")
        formatted.append(
            f"  {dim(f'{label:<8}')} {_format_reconcile_value(label=label, value=value.strip())}"
        )
    return "\n".join(formatted)


def _format_reconcile_value(*, label: str, value: str) -> str:
    if label in {"model", "VDE", "physical"}:
        return blue_bold(value)
    if label == "result":
        return green(value)
    return value
