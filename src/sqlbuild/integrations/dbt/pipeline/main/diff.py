"""Runtime diff pipeline for `sqb dbt diff`."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError, DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.manifest import (
    build_dbt_manifest_index,
    load_dbt_manifest_index,
)
from sqlbuild.integrations.dbt.helpers.mode import enforce_dbt_interop_standard_mode
from sqlbuild.integrations.dbt.helpers.plan_runtime import (
    resolve_dbt_interop_adapter,
    resolve_dbt_manifest_path,
    resolve_dbt_plan_options,
)
from sqlbuild.integrations.dbt.helpers.reuse_from import compile_reuse_from_manifest
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtDiffOptions,
    DbtDiffRun,
    DbtLsNode,
    DbtLsResult,
    DbtReuseFromCompileResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers.diff import (
    execute_dbt_diff,
    mode_label,
    parse_dbt_diff_options,
)
from sqlbuild.integrations.dbt.shared.helpers.connection import resolve_connection_config
from sqlbuild.spec.models.project import DbtReuseFromConfig, resolve_effective_adapter_name


def run_dbt_diff_from_project(
    *,
    project_dir: Path,
    args: tuple[str, ...],
    on_progress: Callable[[str], None] | None = None,
) -> DbtDiffRun:
    """Compile current and reuse manifests and diff selected dbt models."""

    options: DbtDiffOptions = parse_dbt_diff_options(args)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    enforce_dbt_interop_standard_mode(discovered_inputs=discovered_inputs)
    reuse_from: DbtReuseFromConfig = discovered_inputs.project_config.dbt.reuse_from
    if reuse_from.git_ref is None or reuse_from.generate_schema_name_override is None:
        raise DbtInteropConfigError(
            "dbt diff requires [dbt.reuse_from] to be configured",
            code="C346",
            help=(
                "Run sqb dbt init or set [dbt.reuse_from].git_ref and "
                "generate_schema_name_override in sqlbuild_project.toml."
            ),
        )
    dbt_options: DbtCliOptions = resolve_dbt_plan_options(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        dbt_args=options.dbt_args,
    )
    runner: DbtRunner = DbtRunner()
    _report_progress(on_progress, "Compiling dbt project...")
    compile_start: float = time.monotonic()
    compile_result: DbtCommandResult = runner.compile(options=dbt_options)
    if compile_result.returncode != 0:
        raise DbtInteropRuntimeError(
            "dbt compile failed",
            help=compile_result.stderr or compile_result.stdout,
        )
    _report_progress(
        on_progress, f"Compiled dbt project. ({time.monotonic() - compile_start:.2f}s)"
    )
    _report_progress(on_progress, "Loading dbt manifest...")
    current_manifest: DbtManifestIndex = load_dbt_manifest_index(
        manifest_path=resolve_dbt_manifest_path(options=dbt_options)
    )
    _report_progress(on_progress, "Loaded dbt manifest.")
    _report_progress(on_progress, f"Compiling dbt reuse from git ref '{reuse_from.git_ref}'...")
    reuse_start: float = time.monotonic()
    reuse_compile: DbtReuseFromCompileResult = compile_reuse_from_manifest(
        sqlbuild_project_dir=project_dir,
        dbt_options=dbt_options,
        reuse_from=reuse_from,
        runner=runner,
    )
    reuse_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=json.loads(reuse_compile.manifest_contents)
    )
    _report_progress(
        on_progress,
        f"Compiled dbt reuse from git ref '{reuse_from.git_ref}'. "
        f"({time.monotonic() - reuse_start:.2f}s)",
    )
    _report_progress(on_progress, "Resolving dbt selection...")
    selection_start: float = time.monotonic()
    selected_nodes: tuple[DbtLsNode, ...] = _resolve_selected_nodes(
        runner=runner,
        dbt_options=dbt_options,
        options=options,
    )
    _report_progress(
        on_progress, f"Resolved dbt selection. ({time.monotonic() - selection_start:.2f}s)"
    )
    if not selected_nodes:
        raise DbtInteropConfigError(
            "dbt diff selected no dbt models",
            code="C347",
            help="Use --select to choose at least one dbt model.",
        )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_dbt_interop_adapter(adapter_name, project_dir=project_dir)
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=adapter_name,
        discovered_inputs=discovered_inputs,
    )
    _report_progress(on_progress, f"Connecting to {adapter_name}...")
    connect_start: float = time.monotonic()
    connection: Any = adapter.connect(connection_config)
    _report_progress(
        on_progress, f"Connected to {adapter_name}. ({time.monotonic() - connect_start:.2f}s)"
    )
    try:
        _report_progress(on_progress, "Comparing dbt relations...")
        diff_start: float = time.monotonic()
        result: DiffExecutionResult = execute_dbt_diff(
            adapter=adapter,
            connection=connection,
            current_manifest=current_manifest,
            reuse_manifest=reuse_manifest,
            selected_nodes=selected_nodes,
            options=options,
        )
        _report_progress(
            on_progress, f"Compared dbt relations. ({time.monotonic() - diff_start:.2f}s)"
        )
    finally:
        adapter.close(connection)
    return DbtDiffRun(
        result=result,
        from_label=reuse_from.git_ref,
        to_label="current",
        mode_label=mode_label(options),
        verbose=options.verbose,
        max_column_examples=options.max_column_examples,
        max_row_only_examples=options.max_row_only_examples,
    )


def _resolve_selected_nodes(
    *, runner: DbtRunner, dbt_options: DbtCliOptions, options: DbtDiffOptions
) -> tuple[DbtLsNode, ...]:
    ls_result: DbtLsResult = runner.ls(
        options=dbt_options,
        select=options.select,
        exclude=options.exclude,
        resource_types=("model",),
    )
    if ls_result.command.returncode != 0:
        raise DbtInteropRuntimeError(
            "dbt ls failed",
            help=ls_result.command.stderr or ls_result.command.stdout,
        )
    return ls_result.nodes


def _report_progress(on_progress: Callable[[str], None] | None, message: str) -> None:
    if on_progress is not None:
        on_progress(message)
