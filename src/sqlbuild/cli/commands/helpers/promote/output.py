"""Promote command output helpers."""

from __future__ import annotations

from sqlbuild.shared.classes.cli_document import CliDocument
from sqlbuild.shared.helpers.output.cli_style import CliStyle

_MODEL_SET_CAP: int = 20


def format_promote_output(
    *,
    from_virtual_environment: str,
    to_virtual_environment: str,
    status: str,
    promoted_models: tuple[str, ...],
    remaining_stale: tuple[str, ...],
    verbose: bool = False,
    use_color: bool = False,
) -> str:
    """Format virtual promotion output."""

    style: CliStyle = CliStyle(use_color=use_color)
    from_label: str = style.object_name(from_virtual_environment)
    to_label: str = style.object_name(to_virtual_environment)
    status_label: str = "finalized" if status == "finalized" else "working"
    status_value: str = (
        style.success_strong(status_label)
        if status_label == "finalized"
        else style.warning_strong(status_label)
    )
    promoted_count: str = style.value(f"{len(promoted_models):,}")
    remaining_count: str = (
        style.warning_strong(f"{len(remaining_stale):,}")
        if remaining_stale
        else f"{len(remaining_stale):,}"
    )
    doc: CliDocument = CliDocument(style)
    doc.blank()
    doc.header("Virtual promotion complete", suffix=f"{from_label} -> {to_label}")
    doc.line(f"  target status          {status_value}")
    doc.line(f"  promoted models        {promoted_count}")
    if promoted_models:
        for line in _format_model_set_lines(
            label="promoted model set",
            model_names=promoted_models,
            verbose=verbose,
            style=style,
        ):
            doc.line(line)
    doc.line(f"  remaining stale models {remaining_count}")
    if remaining_stale:
        for line in _format_model_set_lines(
            label="remaining stale set",
            model_names=remaining_stale,
            verbose=verbose,
            style=style,
        ):
            doc.line(line)
    return doc.render(trailing_newline=False)


def _format_model_set_lines(
    *, label: str, model_names: tuple[str, ...], verbose: bool, style: CliStyle
) -> list[str]:
    visible: tuple[str, ...] = model_names if verbose else model_names[:_MODEL_SET_CAP]
    label_text: str = style.muted(label)
    lines: list[str] = [f"  {label_text}: " + ", ".join(visible)]
    remaining: int = len(model_names) - len(visible)
    if remaining > 0:
        help_text: str = f"  ... {remaining:,} more; use --verbose to show all"
        lines.append(style.muted(help_text))
    return lines
