"""Promote command output helpers."""

from __future__ import annotations

from sqlbuild.presentation.classes.cli_document import CliDocument
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.completion_line import format_completion_line
from sqlbuild.presentation.types import CompletionState
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus

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
    status_label: str = (
        VirtualEnvironmentStatus.FINALIZED
        if status == VirtualEnvironmentStatus.FINALIZED
        else "working"
    )
    status_value: str = (
        style.success_strong(status_label)
        if status_label == VirtualEnvironmentStatus.FINALIZED
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
    doc.line(
        format_completion_line(
            style=style,
            state=(
                CompletionState.OK
                if status_label == VirtualEnvironmentStatus.FINALIZED
                else CompletionState.WARN
            ),
            label="Virtual promotion complete",
            summary=f"{from_label} -> {to_label}",
        )
    )
    doc.line(f"  {style.label('target status')}          {status_value}")
    doc.line(f"  {style.label('promoted models')}        {promoted_count}")
    if promoted_models:
        for line in _format_model_set_lines(
            label="promoted model set",
            model_names=promoted_models,
            verbose=verbose,
            style=style,
        ):
            doc.line(line)
    doc.line(f"  {style.label('remaining stale models')} {remaining_count}")
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
