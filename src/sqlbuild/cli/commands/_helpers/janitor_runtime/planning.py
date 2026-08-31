"""Janitor command inspection and planning phases."""

from __future__ import annotations

import sys
import time

from sqlbuild.cli.commands._helpers.janitor_retention.checkpoints import (
    checkpoint_candidates,
    checkpoint_protected_relation_keys,
    checkpoint_protected_relation_reasons,
    checkpoint_retention,
)
from sqlbuild.cli.commands._helpers.janitor_retention.detached_environments import (
    detached_environment_candidates,
    detached_environment_protected_relation_keys,
    detached_environment_protected_relation_reasons,
    detached_environment_retention,
    detached_environment_scan_relation_keys,
)
from sqlbuild.cli.commands._helpers.janitor_retention.expired_environments import (
    expired_environment_candidates,
    expired_environment_protected_relation_keys,
    expired_environment_protected_relation_reasons,
    expired_environment_retention,
    expired_environment_scan_relation_keys,
)
from sqlbuild.cli.commands._helpers.janitor_retention.microbatch_replays import (
    active_microbatch_replay_protected_relation_keys,
    active_microbatch_replay_protected_relation_reasons,
    active_microbatch_replay_relations,
)
from sqlbuild.cli.commands._helpers.janitor_retention.state_cleanup import (
    expired_lock_candidates,
    state_backup_candidates,
    state_janitor_retention,
    virtual_state_prune_candidates,
)
from sqlbuild.cli.commands.models import (
    JanitorCompileContext,
    JanitorConnectionContext,
    JanitorInvocation,
    JanitorPlanningResult,
    JanitorRetentionInspection,
    JanitorSettings,
)
from sqlbuild.executor.janitor.main.plan import build_janitor_plan
from sqlbuild.executor.janitor.models import (
    JanitorDirectModeSettings,
    JanitorPlan,
    JanitorRelationKey,
    JanitorRelationScope,
    JanitorStateCandidates,
)
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.virtual.state.models import (
    CheckpointRetentionInspection,
    DetachedVirtualEnvironmentInspection,
    ExpiredVirtualEnvironmentInspection,
    PhysicalRelationRecord,
    StateJanitorInspection,
)


def inspect_janitor_retention(
    *,
    invocation: JanitorInvocation,
    settings: JanitorSettings,
    compile_context: JanitorCompileContext,
) -> JanitorRetentionInspection:
    """Inspect virtual state retention candidates."""

    checkpoint: CheckpointRetentionInspection | None = checkpoint_retention(
        project_dir=invocation.effective_project_dir,
        discovered_inputs=invocation.discovered_inputs,
        virtual_environment_name=compile_context.project.effective_target_name,
    )
    detached_environment: DetachedVirtualEnvironmentInspection | None = (
        detached_environment_retention(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
            retention_days=settings.retention_days,
        )
    )
    expired_environment: ExpiredVirtualEnvironmentInspection | None = expired_environment_retention(
        project_dir=invocation.effective_project_dir,
        discovered_inputs=invocation.discovered_inputs,
        active_virtual_environment_name=compile_context.project.effective_target_name,
        retention_days=settings.retention_days,
    )
    unsuffixed_virtual_environment_name: str | None = _unsuffixed_virtual_environment_name(
        invocation=invocation,
        compile_context=compile_context,
    )
    state: StateJanitorInspection | None = state_janitor_retention(
        project_dir=invocation.effective_project_dir,
        discovered_inputs=invocation.discovered_inputs,
        retention_days=settings.retention_days,
    )
    replay_relations: tuple[PhysicalRelationRecord, ...] = active_microbatch_replay_relations(
        project_dir=invocation.effective_project_dir,
        discovered_inputs=invocation.discovered_inputs,
    )
    return JanitorRetentionInspection(
        checkpoint=checkpoint,
        detached_environment=detached_environment,
        expired_environment=expired_environment,
        state=state,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
        active_microbatch_replay_relations=replay_relations,
    )


def build_janitor_execution_plan(
    *,
    invocation: JanitorInvocation,
    settings: JanitorSettings,
    compile_context: JanitorCompileContext,
    connection_context: JanitorConnectionContext,
    inspection: JanitorRetentionInspection,
) -> JanitorPlanningResult:
    """Build the janitor execution plan from retention inspections."""

    inspect_start: float = time.perf_counter()
    status: TransientStatusReporter = TransientStatusReporter(
        stream=sys.stdout,
        use_color=invocation.use_color,
    )
    status.start("Inspecting warehouse state...")
    protected_relation_keys: frozenset[JanitorRelationKey] = (
        checkpoint_protected_relation_keys(retention=inspection.checkpoint)
        | detached_environment_protected_relation_keys(retention=inspection.detached_environment)
        | expired_environment_protected_relation_keys(retention=inspection.expired_environment)
        | active_microbatch_replay_protected_relation_keys(
            relations=inspection.active_microbatch_replay_relations
        )
    )
    protected_relation_reasons: dict[JanitorRelationKey, str] = (
        detached_environment_protected_relation_reasons(retention=inspection.detached_environment)
    )
    protected_relation_reasons.update(
        expired_environment_protected_relation_reasons(retention=inspection.expired_environment)
    )
    protected_relation_reasons.update(
        checkpoint_protected_relation_reasons(retention=inspection.checkpoint)
    )
    protected_relation_reasons.update(
        active_microbatch_replay_protected_relation_reasons(
            relations=inspection.active_microbatch_replay_relations
        )
    )
    plan: JanitorPlan = build_janitor_plan(
        project=compile_context.project,
        adapter=compile_context.adapter,
        connection=connection_context.connection,
        retention_days=settings.retention_days,
        delete_tracked_only=invocation.discovered_inputs.project_config.janitor.delete_tracked_only,
        exclude_patterns=invocation.discovered_inputs.project_config.janitor.exclude_patterns,
        relation_scope=JanitorRelationScope(
            scan_relation_keys=detached_environment_scan_relation_keys(
                retention=inspection.detached_environment
            )
            | expired_environment_scan_relation_keys(retention=inspection.expired_environment),
            protected_relation_keys=protected_relation_keys,
            protected_relation_reasons=protected_relation_reasons,
        ),
        state_candidates=JanitorStateCandidates(
            checkpoint_candidates=checkpoint_candidates(retention=inspection.checkpoint),
            detached_virtual_environment_candidates=detached_environment_candidates(
                retention=inspection.detached_environment
            ),
            expired_virtual_environment_candidates=expired_environment_candidates(
                retention=inspection.expired_environment
            ),
            state_backup_candidates=state_backup_candidates(retention=inspection.state),
            expired_lock_candidates=expired_lock_candidates(retention=inspection.state),
            virtual_state_prune_candidates=virtual_state_prune_candidates(
                retention=inspection.state
            ),
        ),
        direct_settings=JanitorDirectModeSettings(
            enabled=not invocation.discovered_inputs.project_config.settings.virtual_environments,
            state_history_versions=settings.direct_state_history_versions,
        ),
    )
    status.complete(
        message=f"Inspected warehouse state. ({time.perf_counter() - inspect_start:.2f}s)",
        blank_line_after=True,
    )
    return JanitorPlanningResult(plan=plan)


def _unsuffixed_virtual_environment_name(
    *, invocation: JanitorInvocation, compile_context: JanitorCompileContext
) -> str | None:
    if compile_context.project.effective_target_name is None:
        return None
    return resolve_target_config(
        project_config=invocation.discovered_inputs.project_config,
        local_config=invocation.discovered_inputs.local_config,
        target_name=compile_context.project.effective_target_name,
    ).state.unsuffixed_virtual_env
