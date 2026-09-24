"""Plan safety policies enforced before a direct build executes anything."""

from __future__ import annotations

import sys

from sqlbuild.cli.commands._helpers.build_planning.execution_limits import (
    enforce_model_execution_limit,
    executable_model_count,
)
from sqlbuild.cli.commands._helpers.build_planning.full_refresh import (
    enforce_snapshot_full_refresh_policy,
)
from sqlbuild.cli.commands._helpers.build_planning.retention_decrease import (
    enforce_retention_decrease_policy,
)
from sqlbuild.cli.commands._helpers.build_planning.table_type import (
    enforce_table_type_downgrade_policy,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import BuildCommandRequest, BuildInvocation
from sqlbuild.compiler.migrations.types import MigrationDecision
from sqlbuild.compiler.planner.models import ModelMigrationPlanEntry, PlanOutput


def enforce_build_plan_policies(
    *, request: BuildCommandRequest, invocation: BuildInvocation, plan: PlanOutput
) -> None:
    """Apply migration, execution-limit, and storage safety gates in their required order."""

    _enforce_model_migration_policy(plan=plan)
    enforce_model_execution_limit(
        model_count=executable_model_count(plan=plan),
        target_name=invocation.effective_target_name,
        limits=invocation.execution_limits,
    )
    enforce_snapshot_full_refresh_policy(
        plan=plan,
        snapshots_config=invocation.discovered_inputs.project_config.snapshots,
        allow_snapshot_full_refresh=request.allow_snapshot_full_refresh,
        input_stream=sys.stdin,
        output_stream=sys.stdout,
    )
    enforce_table_type_downgrade_policy(
        plan=plan,
        allow_table_type_downgrade=request.allow_table_type_downgrade,
        input_stream=sys.stdin,
        output_stream=sys.stdout,
    )
    enforce_retention_decrease_policy(
        plan=plan,
        allow_retention_decrease=request.allow_retention_decrease,
        input_stream=sys.stdin,
        output_stream=sys.stdout,
    )


def _enforce_model_migration_policy(*, plan: PlanOutput) -> None:
    """Refuse to build while any planned migration conflicts or is incompatible."""

    blocked: tuple[ModelMigrationPlanEntry, ...] = tuple(
        entry for entry in plan.migration_entries if entry.blocks_build
    )
    if not blocked:
        return
    conflicts: tuple[ModelMigrationPlanEntry, ...] = tuple(
        entry for entry in blocked if entry.decision == MigrationDecision.CONFLICT
    )
    names: str = ", ".join(f"'{entry.model_name}'" for entry in blocked)
    if conflicts:
        raise CliUserError(
            f"model migration conflict for {names}: the destination already exists without a "
            "recorded migration",
            code="M103",
            help=(
                "Set migrate_force true on the model to replace the destination; the replaced "
                "table remains recoverable through warehouse time travel."
            ),
        )
    raise CliUserError(
        f"model migration source is incompatible with {names}",
        code="M104",
        help="Run sqb plan to see the blocking schema differences.",
    )
