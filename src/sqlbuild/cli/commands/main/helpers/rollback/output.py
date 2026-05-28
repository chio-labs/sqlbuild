"""Rollback command output formatting."""

from __future__ import annotations

from sqlbuild.shared.helpers.colors import blue_bold, dim, green_bold, yellow_bold

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

    heading: str = (
        green_bold("Virtual rollback complete") if use_color else "Virtual rollback complete"
    )
    environment_label: str = blue_bold(virtual_environment) if use_color else virtual_environment
    checkpoint_label: str = blue_bold(checkpoint_id) if use_color else checkpoint_id
    status_label: str = (
        green_bold(status)
        if use_color and status == "finalized"
        else yellow_bold(status)
        if use_color
        else status
    )
    model_count: str = (
        blue_bold(f"{len(rolled_back_models):,}") if use_color else f"{len(rolled_back_models):,}"
    )
    lines: list[str] = [
        "",
        heading,
        "",
        f"  virtual environment  {environment_label}",
        f"  checkpoint           {checkpoint_label}",
        f"  status               {status_label}",
        f"  rolled back models   {model_count}",
    ]
    if rolled_back_models:
        lines.extend(
            _format_model_set_lines(
                label="rolled back model set",
                model_names=rolled_back_models,
                verbose=verbose,
                use_color=use_color,
            )
        )
    lines.append("")
    return "\n".join(lines)


def _format_model_set_lines(
    *, label: str, model_names: tuple[str, ...], verbose: bool, use_color: bool
) -> list[str]:
    visible: tuple[str, ...] = model_names if verbose else model_names[:_MODEL_SET_CAP]
    label_text: str = dim(label) if use_color else label
    lines: list[str] = [f"  {label_text}: " + ", ".join(visible)]
    remaining: int = len(model_names) - len(visible)
    if remaining > 0:
        help_text: str = f"  ... {remaining:,} more; use --verbose to show all"
        lines.append(dim(help_text) if use_color else help_text)
    return lines
