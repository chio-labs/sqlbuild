"""Promote command output helpers."""

from __future__ import annotations

from sqlbuild.shared.helpers.colors import blue_bold, dim, green_bold, yellow_bold

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

    title: str = (
        green_bold("Virtual promotion complete") if use_color else "Virtual promotion complete"
    )
    from_label: str = blue_bold(from_virtual_environment) if use_color else from_virtual_environment
    to_label: str = blue_bold(to_virtual_environment) if use_color else to_virtual_environment
    status_label: str = "finalized" if status == "finalized" else "working"
    status_value: str = (
        green_bold(status_label)
        if use_color and status_label == "finalized"
        else yellow_bold(status_label)
        if use_color
        else status_label
    )
    promoted_count: str = (
        blue_bold(f"{len(promoted_models):,}") if use_color else f"{len(promoted_models):,}"
    )
    remaining_count: str = (
        yellow_bold(f"{len(remaining_stale):,}")
        if use_color and remaining_stale
        else f"{len(remaining_stale):,}"
    )
    lines: list[str] = [
        "",
        f"{title}  {from_label} -> {to_label}",
        f"  target status          {status_value}",
        f"  promoted models        {promoted_count}",
    ]
    if promoted_models:
        lines.extend(
            _format_model_set_lines(
                label="promoted model set",
                model_names=promoted_models,
                verbose=verbose,
                use_color=use_color,
            )
        )
    lines.append(f"  remaining stale models {remaining_count}")
    if remaining_stale:
        lines.extend(
            _format_model_set_lines(
                label="remaining stale set",
                model_names=remaining_stale,
                verbose=verbose,
                use_color=use_color,
            )
        )
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
