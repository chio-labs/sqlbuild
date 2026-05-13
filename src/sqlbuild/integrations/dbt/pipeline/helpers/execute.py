"""Execution helpers for dbt interop pipelines."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner, build_dbt_command_argv
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtInteropPlan,
    DbtLsNode,
    DbtManifestIndex,
    DbtManifestModel,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.shared.helpers.colors import dim, orange_bold


def execute_dbt_commands(
    *,
    runner: DbtRunner,
    options: DbtCliOptions,
    merged_argv: tuple[str, ...] | None,
    progress_stream: TextIO,
    stdout_stream: TextIO,
    stderr_stream: TextIO,
    use_color: bool,
) -> int:
    """Execute the merged dbt command, or skip when no dbt work exists."""

    if merged_argv is None:
        progress_stream.write("Skipping dbt: no dbt work selected.\n")
        progress_stream.flush()
        return 0
    argv: tuple[str, ...] = merged_argv
    dbt_execution_label: str = orange_bold("dbt execution") if use_color else "dbt execution"
    dbt_execution_detail_text: str = " ".join(argv[:2]) if len(argv) >= 2 else argv[0]
    dbt_execution_detail: str = (
        dim(dbt_execution_detail_text) if use_color else dbt_execution_detail_text
    )
    progress_stream.write(f"{dbt_execution_label}  {dbt_execution_detail}\n\n")
    progress_stream.write(f"Running dbt: {' '.join(argv)}\n")
    progress_stream.flush()
    result: DbtCommandResult = runner.invoke(argv=argv, cwd=options.project_dir)
    if result.stdout:
        stdout_stream.write(result.stdout)
        stdout_stream.flush()
    if result.stderr:
        stderr_stream.write(result.stderr)
        stderr_stream.flush()
    return result.returncode


def build_merged_dbt_execution_argv(
    *,
    command: DbtInteropCommand,
    options: DbtCliOptions,
    routed_args: tuple[str, ...],
    plan: DbtInteropPlan,
) -> tuple[str, ...] | None:
    """Build the single dbt argv used for execution."""

    if command == DbtInteropCommand.TEST and not plan.dbt_selected_unique_ids:
        return None
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
