"""CLI summary rendering for state lifecycle commands."""

from __future__ import annotations

from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.virtual.state.constants import STATE_TABLE_COLUMNS
from sqlbuild.virtual.state.models import StateBackendConfig


def format_state_lifecycle_summary(
    *,
    title: str,
    config: StateBackendConfig,
    use_color: bool,
    backup_id: str | None = None,
) -> str:
    """Render the post-command state store summary block."""

    style: CliStyle = CliStyle(use_color=use_color)
    rendered_title: str = style.success_strong(title)
    state_label: str = style.success("State store:")
    tables_label: str = style.success("Tables:")
    lines: list[str] = ["", rendered_title, "", state_label]
    lines.append(_summary_row(label="backend", value=config.backend.value, use_color=use_color))
    lines.append(_summary_row(label="schema", value=config.schema, use_color=use_color))
    database: object | None = config.connection.get("database")
    if database is not None:
        lines.append(_summary_row(label="database", value=str(database), use_color=use_color))
    if backup_id is not None:
        lines.append(_summary_row(label="backup", value=backup_id, use_color=use_color))
    lines.append("")
    lines.append(tables_label)
    lines.append(
        _summary_row(
            label="created/validated",
            value=str(len(STATE_TABLE_COLUMNS)),
            use_color=use_color,
        )
    )
    lines.append(
        _summary_row(
            label="current state",
            value=(
                "model_versions, function_versions, physical_relations, "
                "physical_relation_ancestry, virtual_environments, "
                "virtual_environment_node_refs, locks"
            ),
            use_color=use_color,
            emphasize_value=False,
        )
    )
    lines.append(
        _summary_row(
            label="history",
            value=(
                "virtual_environment_checkpoints, virtual_environment_checkpoint_model_refs, "
                "virtual_environment_checkpoint_function_refs, plan_runs, "
                "virtual_environment_model_ref_events, reconcile_events, state_migration_events"
            ),
            use_color=use_color,
            emphasize_value=False,
        )
    )
    lines.append("")
    return "\n".join(lines)


def _summary_row(*, label: str, value: str, use_color: bool, emphasize_value: bool = True) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    rendered_label: str = style.muted(f"{label}:")
    rendered_value: str = style.object_name(value) if emphasize_value else value
    return f"  {rendered_label:<24} {rendered_value}"
