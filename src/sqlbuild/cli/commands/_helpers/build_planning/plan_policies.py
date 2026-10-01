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
from sqlbuild.cli.commands.constants import (
    EXECUTION_LIMIT_BUILD_NOTE,
    EXECUTION_LIMIT_DBT_NOTE,
    MISSING_ORIGIN_BUILD_HELP,
    MISSING_ORIGIN_DBT_HELP,
    RETENTION_DECREASE_BUILD_HELP,
    RETENTION_DECREASE_DBT_HELP,
    SNAPSHOT_FULL_REFRESH_BUILD_HELP,
    SNAPSHOT_FULL_REFRESH_DBT_HELP,
    TABLE_TYPE_DOWNGRADE_BUILD_HELP,
    TABLE_TYPE_DOWNGRADE_DBT_HELP,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import BuildCommandRequest, BuildInvocation, PlanSafetyGates
from sqlbuild.compiler.migrations.types import ColumnMigrationDecision, MigrationDecision
from sqlbuild.compiler.planner.constants import HIDDEN_ORIGIN_REMEDY
from sqlbuild.compiler.planner.models import (
    ColumnMigrationPlanEntry,
    ModelMigrationPlanEntry,
    PlanOutput,
    PlanWarning,
)
from sqlbuild.compiler.planner.types import WarningSeverity
from sqlbuild.spec.contracts.models import ExecutionLimitsConfig, SnapshotsConfig
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
    """Apply every plan safety gate before a direct build executes anything."""

    enforce_plan_safety_policies(
        plan=plan,
        gates=PlanSafetyGates(
            allow_missing_migration_origin=request.allow_missing_migration_origin,
            allow_snapshot_full_refresh=request.allow_snapshot_full_refresh,
            allow_table_type_downgrade=request.allow_table_type_downgrade,
            allow_retention_decrease=request.allow_retention_decrease,
            missing_origin_help=MISSING_ORIGIN_BUILD_HELP,
            snapshot_full_refresh_help=SNAPSHOT_FULL_REFRESH_BUILD_HELP,
            table_type_downgrade_help=TABLE_TYPE_DOWNGRADE_BUILD_HELP,
            retention_decrease_help=RETENTION_DECREASE_BUILD_HELP,
            execution_limit_note=EXECUTION_LIMIT_BUILD_NOTE,
        ),
        snapshots_config=invocation.discovered_inputs.project_config.snapshots,
        target_name=invocation.effective_target_name,
        execution_limits=invocation.execution_limits,
        streams=(sys.stdin, sys.stdout),
    )


def dbt_interop_plan_safety_gates() -> PlanSafetyGates:
    """Gates for sqb dbt, which has no allow flags and confirms only on a terminal."""

    return PlanSafetyGates(
        allow_missing_migration_origin=False,
        allow_snapshot_full_refresh=False,
        allow_table_type_downgrade=False,
        allow_retention_decrease=False,
        missing_origin_help=MISSING_ORIGIN_DBT_HELP,
        snapshot_full_refresh_help=SNAPSHOT_FULL_REFRESH_DBT_HELP,
        table_type_downgrade_help=TABLE_TYPE_DOWNGRADE_DBT_HELP,
        retention_decrease_help=RETENTION_DECREASE_DBT_HELP,
        execution_limit_note=EXECUTION_LIMIT_DBT_NOTE,
    )


def enforce_plan_safety_policies(
    *,
    plan: PlanOutput,
    gates: PlanSafetyGates,
    snapshots_config: SnapshotsConfig,
    target_name: str | None,
    execution_limits: ExecutionLimitsConfig,
    streams: tuple[TextIO, TextIO],
) -> None:
    """Apply migration, execution-limit, and storage safety gates in their required order."""

    input_stream, output_stream = streams
    enforce_migration_plan_policies(
        plan=plan,
        allow_missing_migration_origin=gates.allow_missing_migration_origin,
        non_interactive_help=gates.missing_origin_help,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    _enforce_old_name_policy(plan=plan)
    enforce_model_execution_limit(
        model_count=executable_model_count(plan=plan),
        target_name=target_name,
        limits=execution_limits,
        refusal_note=gates.execution_limit_note,
    )
    enforce_snapshot_full_refresh_policy(
        plan=plan,
        snapshots_config=snapshots_config,
        allow_snapshot_full_refresh=gates.allow_snapshot_full_refresh,
        non_interactive_help=gates.snapshot_full_refresh_help,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    enforce_table_type_downgrade_policy(
        plan=plan,
        allow_table_type_downgrade=gates.allow_table_type_downgrade,
        non_interactive_help=gates.table_type_downgrade_help,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    enforce_retention_decrease_policy(
        plan=plan,
        allow_retention_decrease=gates.allow_retention_decrease,
        non_interactive_help=gates.retention_decrease_help,
        input_stream=input_stream,
        output_stream=output_stream,
    )


def enforce_migration_plan_policies(
    *,
    plan: PlanOutput,
    allow_missing_migration_origin: bool,
    non_interactive_help: str,
    input_stream: TextIO,
    output_stream: TextIO,
) -> None:
    """Refuse blocked model and column migrations, then confirm building past missing origins."""

    _enforce_model_migration_policy(plan=plan)
    _enforce_column_migration_policy(plan=plan)
    _confirm_missing_origins(
        plan=plan,
        allow_missing_migration_origin=allow_missing_migration_origin,
        non_interactive_help=non_interactive_help,
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
    hidden: tuple[ModelMigrationPlanEntry, ...] = tuple(
        entry for entry in blocked if entry.origin_hidden
    )
    if hidden:
        raise CliUserError(
            "model migration origin was built in this target but is not visible for "
            + _origins(hidden)
            + f"; {HIDDEN_ORIGIN_REMEDY}",
            code="M102",
            help="Run sqb plan to see every model migration decision.",
        )
    missing: tuple[ModelMigrationPlanEntry, ...] = tuple(
        entry for entry in blocked if entry.decision == MigrationDecision.ORIGIN_MISSING
    )
    if missing:
        raise CliUserError(
            "model migration origin does not exist for "
            + _origins(missing)
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


def _origins(entries: tuple[ModelMigrationPlanEntry, ...]) -> str:
    return ", ".join(
        f"'{entry.model_name}' (migrate_from {entry.origin.qualified_name or entry.origin.name})"
        for entry in entries
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
    non_interactive_help: str,
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
                and not entry.blocks_build
                and entry.missing_origin_policy == MissingMigrationOriginPolicy.REQUIRE_CONFIRMATION
            }
        )
    )
    if not names or allow_missing_migration_origin:
        return
    listed: str = ", ".join(f"'{name}'" for name in names)
    confirm_typed_action(
        action=f"building {listed} without its missing migrate_from origin",
        non_interactive_help=non_interactive_help,
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
