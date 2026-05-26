"""Rollback command output formatting."""

from __future__ import annotations

from sqlbuild.shared.helpers.colors import blue_bold, dim, green_bold

_MODEL_SET_CAP: int = 20


def format_rollback_output(
    *,
    virtual_environment: str,
    checkpoint_id: str,
    rolled_back_models: tuple[str, ...],
    verbose: bool = False,
    use_color: bool = True,
) -> str:
    """Format virtual rollback result output."""

    heading: str = (
        green_bold("Virtual rollback complete") if use_color else "Virtual rollback complete"
    )
    model_count: str = (
        blue_bold(f"{len(rolled_back_models):,}") if use_color else f"{len(rolled_back_models):,}"
    )
    lines: list[str] = [
        "",
        heading,
        "",
        f"  virtual environment  {virtual_environment}",
        f"  checkpoint           {checkpoint_id}",
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
