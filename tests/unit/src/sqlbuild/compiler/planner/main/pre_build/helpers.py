"""Migration plan display test builders."""

from __future__ import annotations

from sqlbuild.adapter.contract.types import MigrationTransfer
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.migrations.types import (
    ColumnMigrationDecision,
    MigrationCompatibility,
    MigrationDecision,
    MigrationDiscovery,
    MigrationPromotion,
)
from sqlbuild.compiler.planner.main.pre_build.pre_build_work_display import format_pre_build_work
from sqlbuild.compiler.planner.models import (
    ColumnMigrationPlanEntry,
    ModelMigrationPlanEntry,
    PlanOutput,
)
from sqlbuild.presentation.models import DisplayOptions


def migration_entry(
    *,
    decision: MigrationDecision,
    compatibility: MigrationCompatibility = MigrationCompatibility.COMPATIBLE,
    findings: tuple[str, ...] = (),
) -> ModelMigrationPlanEntry:
    """Return one daily_revenue migration moving prod.revenue with the given decision."""

    return ModelMigrationPlanEntry(
        model_name="daily_revenue",
        discovery=MigrationDiscovery.AUTOMATIC,
        decision=decision,
        compatibility=compatibility,
        origin_model="revenue",
        origin=CompiledRelationLocation(
            database=None, schema="prod", name="revenue", qualified_name="prod.revenue"
        ),
        destination=CompiledRelationLocation(
            database=None,
            schema="prod",
            name="daily_revenue",
            qualified_name="prod.daily_revenue",
        ),
        target_name=None,
        transfer=MigrationTransfer.COPY,
        promotion=MigrationPromotion.TRANSACTIONAL_RENAME,
        compatibility_findings=findings,
    )


def styled_migration_text(entry: ModelMigrationPlanEntry) -> str:
    """Return the colour-styled pre-build text for one migration."""

    return "\n".join(
        format_pre_build_work(
            lines=[], plan=PlanOutput(migration_entries=(entry,)), display_options=DisplayOptions()
        )
    )


def column_migration_entry(
    *,
    model_name: str,
    origin_column: str,
    destination_column: str,
    decision: ColumnMigrationDecision,
    discovery: MigrationDiscovery,
) -> ColumnMigrationPlanEntry:
    """Return one column rename on a prod model relation."""

    return ColumnMigrationPlanEntry(
        model_name=model_name,
        destination=CompiledRelationLocation(
            database=None, schema="prod", name=model_name, qualified_name=f"prod.{model_name}"
        ),
        origin_column=origin_column,
        destination_column=destination_column,
        discovery=discovery,
        decision=decision,
        target_name=None,
    )
