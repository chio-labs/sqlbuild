"""Execution helpers for dbt interop pipelines."""

from __future__ import annotations

from collections.abc import Callable
from typing import TextIO

from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError
from sqlbuild.integrations.dbt.helpers.event_stream import execute_dbt_json_event_stream
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner, build_dbt_command_argv
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtInteropPlan,
    DbtLsNode,
    DbtNodeExecutionResult,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.shared.helpers.cli_style import CliStyle


def execute_dbt_commands(
    *,
    runner: DbtRunner,
    options: DbtCliOptions,
    merged_argv: tuple[str, ...] | None,
    progress_stream: TextIO,
    stdout_stream: TextIO,
    stderr_stream: TextIO,
    use_color: bool,
    on_node_result: Callable[[DbtNodeExecutionResult], None] | None = None,
) -> int:
    """Execute the merged dbt command, or skip when no dbt work exists."""

    if merged_argv is None:
        style: CliStyle = CliStyle(use_color=use_color)
        progress_stream.write(style.muted("Skipping dbt: no dbt work selected.") + "\n")
        progress_stream.flush()
        return 0
    argv: tuple[str, ...] = merged_argv
    style: CliStyle = CliStyle(use_color=use_color)
    dbt_execution_label: str = style.dbt_execution_label("dbt execution")
    dbt_execution_detail_text: str = " ".join(argv[:2]) if len(argv) >= 2 else argv[0]
    dbt_execution_detail: str = style.muted(dbt_execution_detail_text)
    progress_stream.write(f"{dbt_execution_label}  {dbt_execution_detail}\n\n")
    progress_stream.flush()
    returncode: int
    returncode, _results = execute_dbt_json_event_stream(
        argv=argv,
        cwd=options.project_dir,
        stream=stdout_stream,
        use_color=use_color,
        target_path=options.target_path,
        on_node_result=on_node_result,
    )
    del runner, stderr_stream, _results
    return returncode


def build_merged_dbt_execution_argv(
    *,
    command: DbtInteropCommand,
    options: DbtCliOptions,
    routed_args: tuple[str, ...],
    plan: DbtInteropPlan,
    replay_on_change: str | None = None,
) -> tuple[str, ...] | None:
    """Build the single dbt argv used for execution."""

    if command == DbtInteropCommand.TEST and not plan.dbt_selected_unique_ids:
        return None
    planned_select_terms: tuple[str, ...] = _planned_dbt_select_terms(plan)
    if plan.dbt_model_plan is not None:
        if not planned_select_terms:
            return None
        pruned_args: tuple[str, ...] = _replace_dbt_select_terms(
            args=_strip_resolved_dbt_options(routed_args),
            select_terms=planned_select_terms,
        )
        pruned_args = _apply_dbt_replay_on_change(
            args=pruned_args,
            replay_on_change=replay_on_change,
            has_planned_model_work=bool(plan.dbt_model_plan.run_unique_ids),
        )
        return build_dbt_command_argv(
            dbt_executable=plan.dbt_command_argv[0],
            command=command.value,
            options=options,
            args=pruned_args,
        )
    if not plan.dbt_selected_unique_ids and not plan.dbt_required_selector_terms:
        return None
    merged_args: tuple[str, ...] = _merge_dbt_select_terms(
        args=_strip_resolved_dbt_options(routed_args),
        extra_terms=plan.dbt_required_selector_terms,
    )
    return build_dbt_command_argv(
        dbt_executable=plan.dbt_command_argv[0],
        command=command.value,
        options=options,
        args=merged_args,
    )


def _apply_dbt_replay_on_change(
    *, args: tuple[str, ...], replay_on_change: str | None, has_planned_model_work: bool
) -> tuple[str, ...]:
    policy: str | None = replay_on_change.strip().lower() if replay_on_change is not None else None
    if policy in (None, "", "forward_only"):
        return args
    if policy != "full":
        raise DbtInteropConfigError(
            "[dbt].replay_on_change must be 'forward_only' or 'full'; "
            "bounded replay policies are not supported for dbt"
        )
    if not has_planned_model_work or "--full-refresh" in args:
        return args
    return ("--full-refresh", *args)


def build_deferred_dbt_relations(
    *, plan: DbtInteropPlan, manifest: DbtManifestIndex
) -> dict[str, RelationInfo]:
    """Build relation overrides for selected dbt models."""

    relations: dict[str, RelationInfo] = {}
    unique_ids: set[str] = set(plan.selection.dbt_required_unique_ids)
    node: DbtLsNode
    for node in plan.dbt_selected_nodes:
        if node.resource_type == "model":
            unique_ids.add(node.unique_id)
    unique_id: str
    for unique_id in unique_ids:
        model: DbtManifestModel | None = manifest.models_by_unique_id.get(unique_id)
        if model is None:
            continue
        relation: RelationInfo = RelationInfo(
            database=model.database,
            schema=model.schema,
            name=model.name,
            relation_type="table",
        )
        relations[model.name] = relation
        relations[f"{model.package_name}.{model.name}"] = relation
    return relations


def build_unblocked_sqlbuild_model_names(plan: DbtInteropPlan) -> tuple[str, ...]:
    """Return selected SQLBuild models not blocked by dbt model planning."""

    if plan.dbt_model_plan is None or not plan.dbt_model_plan.blocked_sqlbuild_model_names:
        return plan.selection.sqlbuild_model_names
    blocked: frozenset[str] = frozenset(plan.dbt_model_plan.blocked_sqlbuild_model_names)
    return tuple(name for name in plan.selection.sqlbuild_model_names if name not in blocked)


def dbt_blocked_exit_code(plan: DbtInteropPlan) -> int:
    """Return non-zero when dbt model planning blocked selected work."""

    if plan.dbt_model_plan is None:
        return 0
    return 1 if plan.dbt_model_plan.blocked_unique_ids else 0


def _strip_resolved_dbt_options(args: tuple[str, ...]) -> tuple[str, ...]:
    value_flags: frozenset[str] = frozenset(
        {"--project-dir", "--profiles-dir", "--target", "--target-path", "--vars", "--state"}
    )
    stripped: list[str] = []
    index: int = 0
    while index < len(args):
        arg: str = args[index]
        if arg in value_flags:
            index += 2
            continue
        if arg == "--defer":
            index += 1
            continue
        stripped.append(arg)
        index += 1
    return tuple(stripped)


def _merge_dbt_select_terms(
    *, args: tuple[str, ...], extra_terms: tuple[str, ...]
) -> tuple[str, ...]:
    if not extra_terms:
        return args
    if "--select" not in args:
        return (*args, "--select", *extra_terms)

    merged: list[str] = []
    index: int = 0
    inserted: bool = False
    while index < len(args):
        token: str = args[index]
        merged.append(token)
        index += 1
        if token != "--select":
            continue
        while index < len(args) and not args[index].startswith("--"):
            merged.append(args[index])
            index += 1
        merged.extend(term for term in extra_terms if term not in merged)
        inserted = True
    if not inserted:
        merged.extend(("--select", *extra_terms))
    return tuple(merged)


def _planned_dbt_select_terms(plan: DbtInteropPlan) -> tuple[str, ...]:
    if plan.dbt_model_plan is None:
        return ()
    if not plan.dbt_model_plan.run_selector_terms:
        return ()
    non_model_selected: tuple[str, ...] = tuple(
        sorted(node.unique_id for node in plan.dbt_selected_nodes if node.resource_type != "model")
    )
    return tuple(sorted(frozenset((*plan.dbt_model_plan.run_selector_terms, *non_model_selected))))


def _replace_dbt_select_terms(
    *, args: tuple[str, ...], select_terms: tuple[str, ...]
) -> tuple[str, ...]:
    stripped: list[str] = []
    index: int = 0
    while index < len(args):
        token: str = args[index]
        if token in {"--select", "--exclude"}:
            index += 1
            while index < len(args) and not args[index].startswith("--"):
                index += 1
            continue
        stripped.append(token)
        index += 1
    return (*stripped, "--select", *select_terms)
