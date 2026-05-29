"""Rollback command output formatting."""

from __future__ import annotations

from sqlbuild.shared.helpers.cli_document import CliDocument
from sqlbuild.shared.helpers.cli_style import CliStyle

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
        style.success_strong(status) if status == "finalized" else style.warning_strong(status)
    )
    model_count: str = style.value(f"{len(rolled_back_models):,}")
    doc: CliDocument = CliDocument(style)
    doc.blank()
    doc.header("Virtual rollback complete")
    doc.blank()
    doc.line(f"  virtual environment  {environment_label}")
    doc.line(f"  checkpoint           {checkpoint_label}")
    doc.line(f"  status               {status_label}")
    doc.line(f"  rolled back models   {model_count}")
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
