"""Janitor command execution phase."""

from __future__ import annotations

from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.cli.commands.helpers.janitor.models import (
    JanitorCompileContext,
    JanitorConnectionContext,
    JanitorInvocation,
    JanitorPlanningResult,
    JanitorRetentionInspection,
)
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.executor.janitor.main.execute import execute_janitor_plan
from sqlbuild.executor.janitor.models import JanitorExecutionResult
from sqlbuild.shared.helpers.identity.naming import resolve_relation_location_qualified_name
from sqlbuild.virtual.executor.main.virtual_target import build_virtual_destination
from sqlbuild.virtual.state.main.checkpoints.delete_checkpoint import (
    delete_virtual_environment_checkpoint,
)
from sqlbuild.virtual.state.main.environments.delete_virtual_environment import (
    delete_virtual_environment,
)
from sqlbuild.virtual.state.main.locks.delete_lock import delete_lock
from sqlbuild.virtual.state.main.python_identities.prune_python_node_identities import (
    prune_unreferenced_python_node_versions,
)
from sqlbuild.virtual.state.main.retention.delete_state_backup import delete_state_backup


def execute_janitor_cleanup(
    *,
    invocation: JanitorInvocation,
    compile_context: JanitorCompileContext,
    connection_context: JanitorConnectionContext,
    inspection: JanitorRetentionInspection,
    planning_result: JanitorPlanningResult,
) -> JanitorExecutionResult:
    """Execute the janitor plan and virtual-state callbacks."""

    return execute_janitor_plan(
        plan=planning_result.plan,
        adapter=compile_context.adapter,
        connection=connection_context.connection,
        delete_checkpoint=lambda candidate: delete_virtual_environment_checkpoint(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
            checkpoint_id=candidate.checkpoint_id,
        ),
        delete_detached_virtual_environment=lambda candidate: delete_virtual_environment(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
            virtual_environment_name=candidate.virtual_environment_name,
        ),
        delete_expired_virtual_environment=lambda candidate: delete_virtual_environment(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
            virtual_environment_name=_drop_logical_vde_views(
                compile_context=compile_context,
                connection_context=connection_context,
                virtual_environment_name=candidate.virtual_environment_name,
                unsuffixed_virtual_environment_name=inspection.unsuffixed_virtual_environment_name,
            ),
        ),
        delete_state_backup=lambda candidate: delete_state_backup(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
            backup_id=candidate.backup_id,
        ),
        delete_expired_lock=lambda candidate: delete_lock(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
            lock_key=candidate.lock_key,
        ),
        prune_virtual_state=lambda candidate: prune_unreferenced_python_node_versions(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
        ),
    )


def _drop_logical_vde_views(
    *,
    compile_context: JanitorCompileContext,
    connection_context: JanitorConnectionContext,
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None,
) -> str:
    recorder: StatementRecorder = StatementRecorder()
    for model in compile_context.project.models:
        virtual_target: CompiledRelationLocation = build_virtual_destination(
            adapter=compile_context.adapter,
            target=model.destination,
            virtual_environment_name=virtual_environment_name,
            unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
        )
        compile_context.adapter.drop_view(
            connection_context.connection,
            destination=resolve_relation_location_qualified_name(
                adapter=compile_context.adapter,
                location=virtual_target,
            ),
            if_exists=True,
            statement_recorder=recorder,
        )
    return virtual_environment_name
