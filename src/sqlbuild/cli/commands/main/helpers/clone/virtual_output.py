"""Virtual clone output helpers."""

from __future__ import annotations

from sqlbuild.shared.helpers.colors import blue_bold, dim, green_bold, yellow_bold
from sqlbuild.virtual.executor.models import VirtualCloneResult


def render_virtual_clone_output(
    *, result: VirtualCloneResult, use_color: bool, verbose: bool
) -> None:
    """Render virtual physical-version hydration output."""

    title: str = green_bold("Virtual clone") if use_color else "Virtual clone"
    source: str = blue_bold(result.source_environment) if use_color else result.source_environment
    target: str = blue_bold(result.target_environment) if use_color else result.target_environment
    print()
    print(f"{title}  {source} -> {target}")
    print(f"  mode                 {result.mode}")
    if result.target_virtual_environment is not None:
        print(f"  target VDE           {result.target_virtual_environment}")
    print("  source state         not used")
    print("  target refs          unchanged")
    print(f"  selected models      {_count(result.selected_count, use_color=use_color)}")
    print(f"  found in source      {_count(result.found_count, use_color=use_color)}")
    print(f"  hydrated             {_count(result.hydrated_count, use_color=use_color)}")
    print(f"  already present      {_count(result.reused_count, use_color=use_color)}")
    missing: str = _warn_count(result.missing_count, use_color=use_color)
    skipped: str = _warn_count(result.skipped_locked_count, use_color=use_color)
    print(f"  missing in source    {missing}")
    print(f"  skipped locked       {skipped}")
    _print_set(
        result=result, action="missing", label="missing", use_color=use_color, verbose=verbose
    )
    _print_set(
        result=result,
        action="skipped_locked",
        label="skipped locked",
        use_color=use_color,
        verbose=verbose,
    )


def is_virtual_clone_success(result: VirtualCloneResult) -> bool:
    return result.missing_count == 0


def _count(count: int, *, use_color: bool) -> str:
    value: str = f"{count:,}"
    return blue_bold(value) if use_color else value


def _warn_count(count: int, *, use_color: bool) -> str:
    value: str = f"{count:,}"
    return yellow_bold(value) if use_color and count else value


def _print_set(
    *, result: VirtualCloneResult, action: str, label: str, use_color: bool, verbose: bool
) -> None:
    names: tuple[str, ...] = tuple(
        item.model_name for item in result.item_results if item.action == action
    )
    if not names:
        return
    limit: int = len(names) if verbose else 20
    rendered_label: str = dim(label) if use_color else label
    print(f"  {rendered_label}: " + ", ".join(names[:limit]))
    if len(names) > limit:
        suffix: str = f"  ... {len(names) - limit:,} more; use --verbose to show all"
        print(dim(suffix) if use_color else suffix)
