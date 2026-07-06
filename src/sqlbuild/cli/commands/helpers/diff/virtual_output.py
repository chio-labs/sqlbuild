"""Virtual diff CLI output helpers."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.diff.models import VirtualDiffRunOutcome
from sqlbuild.shared.classes.cli_document import CliDocument
from sqlbuild.shared.helpers.output.cli_style import CliStyle


def format_virtual_diff_header(
    *,
    from_virtual_environment: str,
    to_virtual_environment: str,
    outcome: VirtualDiffRunOutcome,
    allow_partial_diff: bool,
    verbose: bool,
    use_color: bool,
) -> str:
    """Format the virtual diff summary header."""

    style: CliStyle = CliStyle(use_color=use_color)
    from_label: str = style.object_name(from_virtual_environment)
    to_label: str = style.object_name(to_virtual_environment)
    selected_count: str = style.value(f"{len(outcome.selected_names):,}")
    compared_count: str = style.value(
        f"{len(outcome.selected_names) - len(outcome.skipped_names):,}"
    )
    skipped_count: str = style.muted(f"{len(outcome.skipped_names):,}")
    has_working_vde: bool = outcome.from_working or outcome.to_working
    working_label: str = "yes" if has_working_vde else "no"
    if has_working_vde:
        working_value: str = style.warning_strong(working_label)
        if allow_partial_diff:
            working_value += style.muted(" (partial allowed)")
    else:
        working_value = working_label
    doc: CliDocument = CliDocument(style)
    doc.header("Virtual diff", suffix=f"{from_label} -> {to_label}")
    doc.line(f"  selected models         {selected_count}")
    doc.line(f"  compared models         {compared_count}")
    doc.line(f"  unchanged refs skipped  {skipped_count}")
    doc.line(f"  working VDEs            {working_value}")
    if verbose and (outcome.from_stale or outcome.to_stale):
        if outcome.from_stale:
            doc.line(
                f"  {from_virtual_environment} not current with workspace: "
                + ", ".join(outcome.from_stale)
            )
        if outcome.to_stale:
            doc.line(
                f"  {to_virtual_environment} not current with workspace: "
                + ", ".join(outcome.to_stale)
            )
    return doc.render(trailing_newline=False)
