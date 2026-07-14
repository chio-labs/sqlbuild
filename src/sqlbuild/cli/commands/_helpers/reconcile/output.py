"""Reconcile command output helpers."""

from __future__ import annotations

from sqlbuild.presentation.classes.cli_document import CliDocument
from sqlbuild.presentation.classes.cli_style import CliStyle

_NO_ISSUES_MESSAGE: str = "no issues"
_RECONCILE_ACTION_HEADERS: frozenset[str] = frozenset({"Repair", "Attach"})
_OBJECT_LABELS: frozenset[str] = frozenset({"model", "VDE", "physical"})
_RESULT_LABEL: str = "result"


def format_reconcile_output(*, message: str, use_color: bool) -> str:
    """Format virtual reconcile output."""

    style: CliStyle = CliStyle(use_color=use_color)
    doc: CliDocument = CliDocument(style)
    doc.blank()
    doc.header(text="Virtual reconcile")
    doc.blank()
    doc.line(_format_reconcile_message(message=message, style=style))
    return doc.render()


def _format_reconcile_message(*, message: str, style: CliStyle) -> str:
    if not style.use_color:
        return message
    if _NO_ISSUES_MESSAGE in message:
        return style.value(message)
    lines: list[str] = message.splitlines()
    if not lines or lines[0] not in _RECONCILE_ACTION_HEADERS:
        return message
    formatted: list[str] = [style.success(lines[0])]
    for line in lines[1:]:
        stripped: str = line.strip()
        label, _, value = stripped.partition("  ")
        rendered_value: str = _format_reconcile_value(label=label, value=value.strip(), style=style)
        formatted.append(f"  {style.muted(f'{label:<8}')} {rendered_value}")
    return "\n".join(formatted)


def _format_reconcile_value(*, label: str, value: str, style: CliStyle) -> str:
    if label in _OBJECT_LABELS:
        return style.object_name(value)
    if label == _RESULT_LABEL:
        return style.success(value)
    return value
