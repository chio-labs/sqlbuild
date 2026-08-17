"""Rollback command output formatting."""

from __future__ import annotations

from sqlbuild.presentation.classes.cli_document import CliDocument
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.structure import format_completion_line
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus

_MODEL_SET_CAP: int = 20


def format_rollback_output(
    *,
    virtual_environment: str,
    checkpoint_id: str,
    rolled_back_models: tuple[str, ...],
    status: str,
    verbose: bool = False,
    use_color: bool = True,
) -> str:
    """Format virtual rollback result output."""

    style: CliStyle = CliStyle(use_color=use_color)
    environment_label: str = style.object_name(virtual_environment)
    checkpoint_label: str = style.object_name(checkpoint_id)
    status_label: str = (
        style.success_strong(status)
        if status == VirtualEnvironmentStatus.FINALIZED
        else style.warning_strong(status)
    )
    model_count: str = style.value(f"{len(rolled_back_models):,}")
    doc: CliDocument = CliDocument(style)
    doc.blank()
    doc.line(
        format_completion_line(
            style=style,
            state="ok" if status == VirtualEnvironmentStatus.FINALIZED else "warn",
            label="Virtual rollback complete",
        )
    )
    doc.blank()
    doc.line(f"  {style.label('virtual environment')}  {environment_label}")
    doc.line(f"  {style.label('checkpoint')}           {checkpoint_label}")
    doc.line(f"  {style.label('status')}               {status_label}")
    doc.line(f"  {style.label('rolled back models')}   {model_count}")
    if rolled_back_models:
        for line in _format_model_set_lines(
            label="rolled back model set",
            model_names=rolled_back_models,
            verbose=verbose,
            style=style,
        ):
            doc.line(line)
    doc.blank()
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
