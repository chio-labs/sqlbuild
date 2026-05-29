"""Virtual clone output helpers."""

from __future__ import annotations

from sqlbuild.shared.helpers.cli_document import CliDocument
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.virtual.executor.models import VirtualCloneResult


def render_virtual_clone_output(
    *, result: VirtualCloneResult, use_color: bool, verbose: bool
) -> None:
    """Render virtual physical-version hydration output."""

    style: CliStyle = CliStyle(use_color=use_color)
    doc: CliDocument = CliDocument(style)
    source: str = style.object_name(result.source_environment)
    target: str = style.object_name(result.target_environment)
    doc.blank()
    doc.header("Virtual clone", suffix=f"{source} -> {target}")
    doc.line(f"  mode                 {result.mode}")
    if result.target_virtual_environment is not None:
        doc.line(f"  target VDE           {result.target_virtual_environment}")
    doc.line("  source state         not used")
    doc.line("  target refs          unchanged")
    doc.line(f"  selected models      {_count(result.selected_count, style=style)}")
    doc.line(f"  found in source      {_count(result.found_count, style=style)}")
    doc.line(f"  hydrated             {_count(result.hydrated_count, style=style)}")
    doc.line(f"  already present      {_count(result.reused_count, style=style)}")
    missing: str = _warn_count(result.missing_count, style=style)
    skipped: str = _warn_count(result.skipped_locked_count, style=style)
    doc.line(f"  missing in source    {missing}")
    doc.line(f"  skipped locked       {skipped}")
    _append_set(
        doc=doc, result=result, action="missing", label="missing", style=style, verbose=verbose
    )
    _append_set(
        doc=doc,
        result=result,
        action="skipped_locked",
        label="skipped locked",
        style=style,
        verbose=verbose,
    )
    print(doc.render(), end="")


def is_virtual_clone_success(result: VirtualCloneResult) -> bool:
    return result.missing_count == 0


def _count(count: int, *, style: CliStyle) -> str:
    value: str = f"{count:,}"
    return style.value(value)


def _warn_count(count: int, *, style: CliStyle) -> str:
    value: str = f"{count:,}"
    return style.warning_strong(value) if count else value


def _append_set(
    *,
    doc: CliDocument,
    result: VirtualCloneResult,
    action: str,
    label: str,
    style: CliStyle,
    verbose: bool,
) -> None:
    names: tuple[str, ...] = tuple(
        item.model_name for item in result.item_results if item.action == action
    )
    if not names:
        return
    limit: int = len(names) if verbose else 20
    rendered_label: str = style.muted(label)
    doc.line(f"  {rendered_label}: " + ", ".join(names[:limit]))
    if len(names) > limit:
        suffix: str = f"  ... {len(names) - limit:,} more; use --verbose to show all"
        doc.line(style.muted(suffix))
