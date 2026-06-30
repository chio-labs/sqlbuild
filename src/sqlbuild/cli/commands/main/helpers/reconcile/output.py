"""Reconcile command output helpers."""

from __future__ import annotations

from sqlbuild.shared.classes.cli_document import CliDocument
from sqlbuild.shared.helpers.cli_style import CliStyle


def format_reconcile_output(*, message: str, use_color: bool) -> str:
    """Format virtual reconcile output."""

    style: CliStyle = CliStyle(use_color=use_color)
    doc: CliDocument = CliDocument(style)
    doc.blank()
    doc.header("Virtual reconcile")
    doc.blank()
    doc.line(_format_reconcile_message(message=message, style=style))
    return doc.render()


def _format_reconcile_message(*, message: str, style: CliStyle) -> str:
    if not style.use_color:
        return message
    if "no issues" in message:
        return style.value(message)
    lines: list[str] = message.splitlines()
    if not lines or lines[0] not in {"Repair", "Attach"}:
        return message
    formatted: list[str] = [style.success(lines[0])]
    for line in lines[1:]:
        stripped: str = line.strip()
        label, _, value = stripped.partition("  ")
        rendered_value: str = _format_reconcile_value(label=label, value=value.strip(), style=style)
        formatted.append(f"  {style.muted(f'{label:<8}')} {rendered_value}")
    return "\n".join(formatted)


def _format_reconcile_value(*, label: str, value: str, style: CliStyle) -> str:
    if label in {"model", "VDE", "physical"}:
        return style.object_name(value)
    if label == "result":
        return style.success(value)
    return value
