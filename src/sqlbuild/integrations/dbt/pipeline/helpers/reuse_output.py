"""dbt reuse execution output formatting."""

from __future__ import annotations

from collections.abc import Sequence

from sqlbuild.integrations.dbt.models import DbtReusePlanEntry, DbtReusePlanningResult
from sqlbuild.integrations.dbt.types import DbtReusePlanAction
from sqlbuild.shared.helpers.alignment import format_aligned_name_value, resolve_name_column_width
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.display import DisplayOptions, append_overflow_line, visible_entries
from sqlbuild.shared.helpers.summary_footer import format_summary_footer


def format_dbt_reuse_execution_output(
    *,
    plan: DbtReusePlanningResult,
    reused_unique_ids: tuple[str, ...],
    baseline_reused_unique_ids: tuple[str, ...],
    use_color: bool,
    dbt_execution_will_run: bool,
    display_options: DisplayOptions | None = None,
) -> str:
    """Format completed physical dbt reuse work for human CLI output."""

    if not reused_unique_ids and not baseline_reused_unique_ids:
        return ""
    options: DisplayOptions = display_options or DisplayOptions()
    style: CliStyle = CliStyle(use_color=use_color)
    executed_ids: tuple[str, ...] = (*reused_unique_ids, *baseline_reused_unique_ids)
    entries_by_unique_id: dict[str, DbtReusePlanEntry] = {
        entry.unique_id: entry for entry in plan.entries
    }
    name_width: int = resolve_name_column_width(executed_ids)
    lines: list[str] = []
    detail: str = "pre-phase before dbt execution" if dbt_execution_will_run else "pre-phase"
    lines.append(f"{style.dbt_execution_label('dbt reuse')}  {style.muted(detail)}")
    visible_ids: Sequence[str] = visible_entries(executed_ids, options=options)
    unique_id: str
    for unique_id in visible_ids:
        entry: DbtReusePlanEntry | None = entries_by_unique_id.get(unique_id)
        action: DbtReusePlanAction | None = entry.action if entry is not None else None
        lines.append(
            "  "
            + format_aligned_name_value(
                plain_name=unique_id,
                styled_name=style.dbt_object_name(unique_id),
                value=f"{style.status('OK'):<6} {_dbt_reuse_execution_action_label(action)}",
                name_column_width=name_width,
            )
        )
    append_overflow_line(
        lines,
        total_count=len(executed_ids),
        visible_count=len(visible_ids),
        indent="  ",
        options=options,
    )
    lines.append("")
    lines.append(
        format_summary_footer(
            counts=(
                ("REUSED", len(reused_unique_ids)),
                ("BASELINE_REUSED", len(baseline_reused_unique_ids)),
                ("TOTAL", len(executed_ids)),
            ),
            use_color=use_color,
        )
    )
    return "\n".join(lines)


def _dbt_reuse_execution_action_label(action: DbtReusePlanAction | None) -> str:
    if action == DbtReusePlanAction.SEEDED_REUSE:
        return "baseline reuse before dbt catch-up"
    return "reuse"
