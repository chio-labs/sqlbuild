"""Janitor command warehouse inspection and planning phases."""

from __future__ import annotations

import sys
import time

from sqlbuild.cli.commands.models import (
    JanitorCompileContext,
    JanitorConnectionContext,
    JanitorInvocation,
    JanitorPlanningResult,
    JanitorSettings,
)
from sqlbuild.executor.janitor.main.plan import build_janitor_plan
from sqlbuild.executor.janitor.models import JanitorDirectModeSettings, JanitorPlan
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


def build_janitor_execution_plan(
    *,
    invocation: JanitorInvocation,
    settings: JanitorSettings,
    compile_context: JanitorCompileContext,
    connection_context: JanitorConnectionContext,
) -> JanitorPlanningResult:
    """Build the janitor execution plan from warehouse facts."""

    inspect_start: float = time.perf_counter()
    status: TransientStatusReporter = TransientStatusReporter(
        stream=sys.stdout,
        use_color=invocation.use_color,
    )
    status.start("Inspecting warehouse state...")
    with OperationLifecycle(
        operation_kind="janitor", operation_name="janitor_candidate_planning"
    ) as lifecycle:
        plan: JanitorPlan = build_janitor_plan(
            project=compile_context.project,
            adapter=compile_context.adapter,
            connection=connection_context.connection,
            retention_days=settings.retention_days,
            delete_tracked_only=invocation.discovered_inputs.project_config.janitor.delete_tracked_only,
            exclude_patterns=invocation.discovered_inputs.project_config.janitor.exclude_patterns,
            direct_settings=JanitorDirectModeSettings(
                enabled=True,
                state_history_versions=settings.direct_state_history_versions,
                archive_retention_days=settings.archive_retention_days,
            ),
        )
        lifecycle.completed(metadata={"item_count": _janitor_candidate_count(plan)})
    status.complete(
        message=f"Inspected warehouse state. ({time.perf_counter() - inspect_start:.2f}s)",
        blank_line_after=True,
    )
    return JanitorPlanningResult(plan=plan)


def _janitor_candidate_count(plan: JanitorPlan) -> int:
    return sum(
        len(candidates)
        for candidates in (
            plan.candidates,
            plan.archive_deletion_candidates,
            plan.query_diff_artifact_candidates,
            plan.direct_state_prune_candidates,
        )
    )
