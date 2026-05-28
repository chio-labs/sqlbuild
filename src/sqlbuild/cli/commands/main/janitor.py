"""CLI janitor command entry point."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.cli.commands.main.helpers.janitor.checkpoints import (
    checkpoint_candidates,
    checkpoint_protected_relation_keys,
    checkpoint_protected_relation_reasons,
    checkpoint_retention,
)
from sqlbuild.cli.commands.main.helpers.janitor.detached_environments import (
    detached_environment_candidates,
    detached_environment_protected_relation_keys,
    detached_environment_protected_relation_reasons,
    detached_environment_retention,
    detached_environment_scan_relation_keys,
)
from sqlbuild.cli.commands.main.helpers.janitor.expired_environments import (
    expired_environment_candidates,
    expired_environment_protected_relation_keys,
    expired_environment_protected_relation_reasons,
    expired_environment_retention,
    expired_environment_scan_relation_keys,
)
from sqlbuild.cli.commands.main.helpers.janitor.output import (
    confirmation_text,
    environment_label,
    write_disabled,
    write_plan,
)
from sqlbuild.cli.commands.main.helpers.janitor.state_cleanup import (
    expired_lock_candidates,
    state_backup_candidates,
    state_janitor_retention,
)
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_connection_config
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.main.shared.helpers.status import TransientStatusReporter
from sqlbuild.compiler.compile.models.core import CompiledProject, CompiledRelationTarget
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.project import compile_project
from sqlbuild.executor.janitor.main.execute import execute_janitor_plan
from sqlbuild.executor.janitor.main.plan import build_janitor_plan
from sqlbuild.executor.janitor.models import (
    JanitorExecutionResult,
    JanitorPlan,
    JanitorRelationKey,
)
from sqlbuild.shared.helpers.colors import green, supports_color
from sqlbuild.shared.helpers.naming import resolve_target_qualified_name
from sqlbuild.spec.models.environments import resolve_environment_config
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.virtual.executor.main.virtual_target import build_virtual_target
from sqlbuild.virtual.state.main.delete_checkpoint import delete_virtual_environment_checkpoint
from sqlbuild.virtual.state.main.delete_lock import delete_lock
from sqlbuild.virtual.state.main.delete_state_backup import delete_state_backup
from sqlbuild.virtual.state.main.delete_virtual_environment import delete_virtual_environment
from sqlbuild.virtual.state.models import (
    CheckpointRetentionInspection,
    DetachedVirtualEnvironmentInspection,
    ExpiredVirtualEnvironmentInspection,
    StateJanitorInspection,
)


def run_janitor(
    project_dir: Path | None,
    no_color: bool = False,
    auto_approve: bool = False,
    retention_days: int | None = None,
) -> int:
    """Execute the janitor command."""

    use_color: bool = not no_color and supports_color()
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    status: TransientStatusReporter = TransientStatusReporter(
        stream=sys.stdout,
        use_color=use_color,
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    if not discovered_inputs.project_config.janitor.enabled:
        write_disabled(stream=sys.stdout, use_color=use_color)
        return 0
    effective_retention_days: int = (
        retention_days
        if retention_days is not None
        else discovered_inputs.project_config.janitor.retention_days
    )
    if effective_retention_days < 0:
        raise CliUserError("janitor --retention-days must be >= 0", code="C501")

    effective_adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        effective_adapter_name, project_dir=effective_project_dir
    )
    compile_start: float = time.perf_counter()
    status.start("Compiling project...")
    project: CompiledProject = compile_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
    )
    status.complete(f"Compiled project. ({time.perf_counter() - compile_start:.2f}s)")
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=project.effective_connection,
        project_dir=effective_project_dir,
        adapter_name=effective_adapter_name,
    )
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=effective_adapter_name,
        stream=sys.stdout,
        use_color=use_color,
    )
    connection_start: float = time.perf_counter()
    connection_progress.on_connection_start(1)
    try:
        connection: object = adapter.connect(connection_config)
    except BaseException:
        connection_progress.on_connection_error(1, time.perf_counter() - connection_start)
        raise
    connection_progress.on_connection_complete(1, time.perf_counter() - connection_start)
    try:
        inspect_start: float = time.perf_counter()
        status.start("Inspecting warehouse state...")
        retention: CheckpointRetentionInspection | None = checkpoint_retention(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            virtual_environment_name=project.effective_environment_name,
        )
        detached_retention: DetachedVirtualEnvironmentInspection | None = (
            detached_environment_retention(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
                retention_days=effective_retention_days,
            )
        )
        expired_retention: ExpiredVirtualEnvironmentInspection | None = (
            expired_environment_retention(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
                active_virtual_environment_name=project.effective_environment_name,
                retention_days=effective_retention_days,
            )
        )
        unsuffixed_virtual_environment_name: str | None = None
        if project.effective_environment_name is not None:
            unsuffixed_virtual_environment_name = resolve_environment_config(
                project_config=discovered_inputs.project_config,
                local_config=discovered_inputs.local_config,
                environment_name=project.effective_environment_name,
            ).state.unsuffixed_virtual_env
        state_retention: StateJanitorInspection | None = state_janitor_retention(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            retention_days=effective_retention_days,
        )
        protected_relation_keys: frozenset[JanitorRelationKey] = (
            checkpoint_protected_relation_keys(
                retention=retention,
            )
            | detached_environment_protected_relation_keys(retention=detached_retention)
            | expired_environment_protected_relation_keys(retention=expired_retention)
        )
        protected_relation_reasons: dict[JanitorRelationKey, str] = (
            detached_environment_protected_relation_reasons(
                retention=detached_retention,
            )
        )
        protected_relation_reasons.update(
            expired_environment_protected_relation_reasons(retention=expired_retention)
        )
        protected_relation_reasons.update(
            checkpoint_protected_relation_reasons(retention=retention)
        )
        plan: JanitorPlan = build_janitor_plan(
            project=project,
            adapter=adapter,
            connection=connection,
            retention_days=effective_retention_days,
            delete_tracked_only=discovered_inputs.project_config.janitor.delete_tracked_only,
            exclude_patterns=discovered_inputs.project_config.janitor.exclude_patterns,
            scan_relation_keys=detached_environment_scan_relation_keys(
                retention=detached_retention,
            )
            | expired_environment_scan_relation_keys(retention=expired_retention),
            protected_relation_keys=protected_relation_keys,
            protected_relation_reasons=protected_relation_reasons,
            checkpoint_candidates=checkpoint_candidates(
                retention=retention,
            ),
            detached_virtual_environment_candidates=detached_environment_candidates(
                retention=detached_retention,
            ),
            expired_virtual_environment_candidates=expired_environment_candidates(
                retention=expired_retention,
            ),
            state_backup_candidates=state_backup_candidates(retention=state_retention),
            expired_lock_candidates=expired_lock_candidates(retention=state_retention),
        )
        status.complete(
            f"Inspected warehouse state. ({time.perf_counter() - inspect_start:.2f}s)",
            blank_line_after=True,
        )
        write_plan(plan=plan, stream=sys.stdout, use_color=use_color)
        if (
            not plan.candidates
            and not plan.checkpoint_candidates
            and not plan.detached_virtual_environment_candidates
            and not plan.expired_virtual_environment_candidates
            and not plan.state_backup_candidates
            and not plan.expired_lock_candidates
        ):
            return 0
        if not auto_approve and not _confirm(plan=plan):
            sys.stdout.write("Janitor cancelled.\n")
            return 1
        result: JanitorExecutionResult = execute_janitor_plan(
            plan=plan,
            adapter=adapter,
            connection=connection,
            delete_checkpoint=lambda candidate: delete_virtual_environment_checkpoint(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
                checkpoint_id=candidate.checkpoint_id,
            ),
            delete_detached_virtual_environment=lambda candidate: delete_virtual_environment(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
                virtual_environment_name=candidate.virtual_environment_name,
            ),
            delete_expired_virtual_environment=lambda candidate: delete_virtual_environment(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
                virtual_environment_name=_drop_logical_vde_views(
                    project=project,
                    adapter=adapter,
                    connection=connection,
                    virtual_environment_name=candidate.virtual_environment_name,
                    unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
                ),
            ),
            delete_state_backup=lambda candidate: delete_state_backup(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
                backup_id=candidate.backup_id,
            ),
            delete_expired_lock=lambda candidate: delete_lock(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
                lock_key=candidate.lock_key,
            ),
        )
        deleted_state_count: int = (
            len(result.deleted_checkpoints)
            + len(result.deleted_detached_virtual_environments)
            + len(result.deleted_expired_virtual_environments)
            + len(result.deleted_state_backups)
            + len(result.deleted_expired_locks)
        )
        non_checkpoint_state_count: int = deleted_state_count - len(result.deleted_checkpoints)
        if non_checkpoint_state_count:
            deleted_message: str = (
                f"Deleted {len(result.deleted)} objects and {deleted_state_count} state items."
            )
        elif result.deleted_checkpoints:
            deleted_message = (
                f"Deleted {len(result.deleted)} objects and "
                f"{len(result.deleted_checkpoints)} checkpoints."
            )
        else:
            deleted_message = f"Deleted {len(result.deleted)} objects."
        sys.stdout.write((green(deleted_message) if use_color else deleted_message) + "\n")
        return 0
    finally:
        adapter.close(connection)


def _confirm(*, plan: JanitorPlan) -> bool:
    expected: str = confirmation_text(plan)
    state_candidate_count: int = (
        len(plan.checkpoint_candidates)
        + len(plan.detached_virtual_environment_candidates)
        + len(plan.expired_virtual_environment_candidates)
        + len(plan.state_backup_candidates)
        + len(plan.expired_lock_candidates)
    )
    if state_candidate_count:
        deletion_count: int = len(plan.candidates) + state_candidate_count
        sys.stdout.write(
            f"Janitor will delete {deletion_count} items from {environment_label(plan)}.\n"
        )
    else:
        sys.stdout.write(
            f"Janitor will delete {len(plan.candidates)} objects from {environment_label(plan)}.\n"
        )
    if plan.retention_days == 0:
        sys.stdout.write("Retention: disabled (0 days)\n")
        sys.stdout.write("Age metadata will not be checked.\n")
    else:
        sys.stdout.write(f"Retention: {plan.retention_days} days\n")
    sys.stdout.write(f"\nType `{expected}` to continue: ")
    sys.stdout.flush()
    try:
        response: str = input()
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        return False
    return response == expected


def _drop_logical_vde_views(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: object,
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None,
) -> str:
    recorder: StatementRecorder = StatementRecorder()
    for model in project.models:
        virtual_target: CompiledRelationTarget = build_virtual_target(
            adapter=adapter,
            target=model.target,
            virtual_environment_name=virtual_environment_name,
            unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
        )
        adapter.drop_view(
            connection,
            target=resolve_target_qualified_name(adapter=adapter, target=virtual_target),
            if_exists=True,
            statement_recorder=recorder,
        )
    return virtual_environment_name
