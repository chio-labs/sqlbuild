"""CLI janitor command entry point."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
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
from sqlbuild.cli.commands.main.helpers.janitor.output import (
    confirmation_text,
    environment_label,
    write_disabled,
    write_plan,
)
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_connection_config
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.main.shared.helpers.status import TransientStatusReporter
from sqlbuild.compiler.compile.models.core import CompiledProject
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
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.virtual.state.main.delete_checkpoint import delete_virtual_environment_checkpoint
from sqlbuild.virtual.state.main.delete_virtual_environment import delete_virtual_environment
from sqlbuild.virtual.state.models import (
    CheckpointRetentionInspection,
    DetachedVirtualEnvironmentInspection,
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
    status.start("Compiling project...")
    project: CompiledProject = compile_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
    )
    status.complete("Compiled project.")
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
    connection_progress.on_connection_start(1)
    connection_start: float = time.perf_counter()
    connection: object = adapter.connect(connection_config)
    connection_progress.on_connection_complete(1, time.perf_counter() - connection_start)
    try:
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
        protected_relation_keys: frozenset[JanitorRelationKey] = checkpoint_protected_relation_keys(
            retention=retention,
        ) | detached_environment_protected_relation_keys(retention=detached_retention)
        protected_relation_reasons: dict[JanitorRelationKey, str] = (
            detached_environment_protected_relation_reasons(
                retention=detached_retention,
            )
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
            ),
            protected_relation_keys=protected_relation_keys,
            protected_relation_reasons=protected_relation_reasons,
            checkpoint_candidates=checkpoint_candidates(
                retention=retention,
            ),
            detached_virtual_environment_candidates=detached_environment_candidates(
                retention=detached_retention,
            ),
        )
        status.complete("Inspected warehouse state.", blank_line_after=True)
        write_plan(plan=plan, stream=sys.stdout, use_color=use_color)
        if (
            not plan.candidates
            and not plan.checkpoint_candidates
            and not plan.detached_virtual_environment_candidates
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
        )
        if result.deleted_detached_virtual_environments:
            deleted_state_count: int = len(result.deleted_checkpoints) + len(
                result.deleted_detached_virtual_environments
            )
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
    state_candidate_count: int = len(plan.checkpoint_candidates) + len(
        plan.detached_virtual_environment_candidates
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
    response: str = input()
    return response == expected
