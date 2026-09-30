"""Plan safety policies enforced before a direct build executes anything."""

from __future__ import annotations

import sys
from typing import TextIO

from sqlbuild.cli.commands._helpers.build_planning.confirmation import confirm_typed_action
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
from sqlbuild.compiler.migrations.types import ColumnMigrationDecision, MigrationDecision
from sqlbuild.compiler.planner.models import (
    ColumnMigrationPlanEntry,
    ModelMigrationPlanEntry,
    PlanOutput,
    PlanWarning,
)
from sqlbuild.compiler.planner.types import WarningSeverity
from sqlbuild.spec.contracts.types import MissingMigrationOriginPolicy

_OLD_NAME_CODES: frozenset[str] = frozenset({"M114", "P008"})
_COLUMN_BLOCK_CODES: dict[ColumnMigrationDecision, str] = {
    ColumnMigrationDecision.SOURCE_MISSING: "M109",
    ColumnMigrationDecision.CONFLICT: "M110",
    ColumnMigrationDecision.STILL_PRODUCED: "M111",
    ColumnMigrationDecision.UNSUPPORTED: "M112",
}


def enforce_build_plan_policies(
    *, request: BuildCommandRequest, invocation: BuildInvocation, plan: PlanOutput
) -> None:
    """Apply migration, execution-limit, and storage safety gates in their required order."""

    enforce_migration_plan_policies(
        plan=plan,
        allow_missing_migration_origin=request.allow_missing_migration_origin,
        input_stream=sys.stdin,
        output_stream=sys.stdout,
    )
    _enforce_old_name_policy(plan=plan)
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


def enforce_migration_plan_policies(
    *,
    plan: PlanOutput,
    allow_missing_migration_origin: bool,
    input_stream: TextIO,
    output_stream: TextIO,
) -> None:
    """Refuse blocked model and column migrations, then confirm building past missing origins."""

    _enforce_model_migration_policy(plan=plan)
    _enforce_column_migration_policy(plan=plan)
    _confirm_missing_origins(
        plan=plan,
        allow_missing_migration_origin=allow_missing_migration_origin,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def _enforce_model_migration_policy(*, plan: PlanOutput) -> None:
    """Refuse to build while any planned migration conflicts or is incompatible."""

    blocked: tuple[ModelMigrationPlanEntry, ...] = tuple(
        entry for entry in plan.migration_entries if entry.blocks_build
    )
    if not blocked:
        return
    missing: tuple[ModelMigrationPlanEntry, ...] = tuple(
        entry for entry in blocked if entry.decision == MigrationDecision.ORIGIN_MISSING
    )
    if missing:
        raise CliUserError(
            "model migration origin does not exist for "
            + ", ".join(
                f"'{entry.model_name}' (migrate_from "
                f"{entry.origin.qualified_name or entry.origin.name})"
                for entry in missing
            )
            + " and no recorded migration into it was found, and this target sets "
            "missing_migration_origin = deny; if the migration already happened elsewhere or is "
            "no longer needed, remove migrate_from from the model header",
            code="M102",
            help="Run sqb plan to see every model migration decision.",
        )
    conflicts: tuple[ModelMigrationPlanEntry, ...] = tuple(
        entry for entry in blocked if entry.decision == MigrationDecision.CONFLICT
    )
    names: str = ", ".join(f"'{entry.model_name}'" for entry in blocked)
    if conflicts:
        raise CliUserError(
            f"model migration conflict for {names}: the destination already exists with its "
            "own build history and no recorded migration",
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


def _enforce_column_migration_policy(*, plan: PlanOutput) -> None:
    """Refuse to build while any declared column rename cannot be applied safely."""

    blocked: tuple[ColumnMigrationPlanEntry, ...] = tuple(
        entry for entry in plan.column_migration_entries if entry.blocks_build
    )
    if not blocked:
        return
    raise CliUserError(
        "column migrations are blocked for "
        + ", ".join(
            f"'{entry.model_name}' ({entry.destination_column} migrate_from "
            f"{entry.origin_column}: {entry.decision.label})"
            for entry in blocked
        ),
        code=_COLUMN_BLOCK_CODES.get(blocked[0].decision, "M109"),
        help="Run sqb plan to see why each column rename cannot be applied.",
    )


def _confirm_missing_origins(
    *,
    plan: PlanOutput,
    allow_missing_migration_origin: bool,
    input_stream: TextIO,
    output_stream: TextIO,
) -> None:
    """Confirm before building past declared migrations whose origin is missing."""

    names: tuple[str, ...] = tuple(
        sorted(
            {
                entry.model_name
                for entry in (*plan.migration_entries, *plan.column_migration_entries)
                if entry.origin_missing
                and entry.missing_origin_policy == MissingMigrationOriginPolicy.REQUIRE_CONFIRMATION
            }
        )
    )
    if not names or allow_missing_migration_origin:
        return
    listed: str = ", ".join(f"'{name}'" for name in names)
    confirm_typed_action(
        action=f"building {listed} without its missing migrate_from origin",
        flag="--allow-missing-migration-origin",
        warning=f"The migrate_from origin of {listed} does not exist in this target; nothing "
        "will be migrated.",
        expected=(
            f"build {names[0]} without its migration"
            if len(names) == 1
            else f"build {len(names)} models without their migrations"
        ),
        input_stream=input_stream,
        output_stream=output_stream,
        code="M102",
    )


def _enforce_old_name_policy(*, plan: PlanOutput) -> None:
    """Refuse to build over a compatibility view or while code reads an old name."""

    errors: tuple[PlanWarning, ...] = tuple(
        warning
        for warning in plan.warnings
        if warning.severity == WarningSeverity.ERROR and warning.code in _OLD_NAME_CODES
    )
    if not errors:
        return
    raise CliUserError(
        "; ".join(warning.message for warning in errors),
        code=errors[0].code or "M114",
        help="Run sqb plan to see every compatibility view and old-name reference.",
    )
