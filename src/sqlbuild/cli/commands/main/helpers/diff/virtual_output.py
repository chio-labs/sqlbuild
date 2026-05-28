"""Virtual diff CLI output helpers."""

from __future__ import annotations

from sqlbuild.shared.helpers.colors import blue_bold, dim, green_bold, yellow_bold


def format_virtual_diff_header(
    *,
    from_virtual_environment: str,
    to_virtual_environment: str,
    selected_names: tuple[str, ...],
    skipped_names: tuple[str, ...],
    from_stale: tuple[str, ...],
    to_stale: tuple[str, ...],
    from_working: bool,
    to_working: bool,
    allow_partial_diff: bool,
    verbose: bool,
    use_color: bool,
) -> str:
    """Format the virtual diff summary header."""

    title: str = green_bold("Virtual diff") if use_color else "Virtual diff"
    from_label: str = blue_bold(from_virtual_environment) if use_color else from_virtual_environment
    to_label: str = blue_bold(to_virtual_environment) if use_color else to_virtual_environment
    selected_count: str = _format_count(len(selected_names), use_color=use_color)
    compared_count: str = _format_count(
        len(selected_names) - len(skipped_names), use_color=use_color
    )
    skipped_count: str = _format_skipped_count(len(skipped_names), use_color=use_color)
    has_working_vde: bool = from_working or to_working
    working_label: str = "yes" if has_working_vde else "no"
    if has_working_vde:
        working_value: str = yellow_bold(working_label) if use_color else working_label
        if allow_partial_diff:
            suffix: str = dim(" (partial allowed)") if use_color else " (partial allowed)"
            working_value += suffix
    else:
        working_value = working_label
    lines: list[str] = [
        f"{title}  {from_label} -> {to_label}",
        f"  selected models         {selected_count}",
        f"  compared models         {compared_count}",
        f"  unchanged refs skipped  {skipped_count}",
        f"  working VDEs            {working_value}",
    ]
    if verbose and (from_stale or to_stale):
        if from_stale:
            lines.append(
                f"  {from_virtual_environment} not current with workspace: " + ", ".join(from_stale)
            )
        if to_stale:
            lines.append(
                f"  {to_virtual_environment} not current with workspace: " + ", ".join(to_stale)
            )
    return "\n".join(lines)


def _format_count(count: int, *, use_color: bool) -> str:
    value: str = f"{count:,}"
    return blue_bold(value) if use_color else value


def _format_skipped_count(count: int, *, use_color: bool) -> str:
    value: str = f"{count:,}"
    return dim(value) if use_color else value
