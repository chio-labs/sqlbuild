"""Runtime clone pipeline for `sqb dbt clone`."""

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
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError, DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.cli.mode import enforce_dbt_interop_standard_mode
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.manifest.core import (
    build_dbt_manifest_index,
    load_dbt_manifest_index,
)
from sqlbuild.integrations.dbt.helpers.planning.runtime import (
    resolve_dbt_interop_adapter,
    resolve_dbt_manifest_path,
    resolve_dbt_plan_options,
)
from sqlbuild.integrations.dbt.helpers.reuse.production_ref import compile_production_ref_manifest
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCloneOptions,
    DbtCloneRun,
    DbtCommandResult,
    DbtLsNode,
    DbtLsResult,
    DbtProductionRefCompileResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers.clone import (
    execute_dbt_clone,
    parse_dbt_clone_options,
)
from sqlbuild.integrations.dbt.shared.helpers.connection import resolve_connection_config
from sqlbuild.integrations.dbt.types import DbtSupportedResourceType
from sqlbuild.spec.models.project import DbtProductionRefConfig, resolve_effective_adapter_name


def run_dbt_clone_from_project(
    *,
    project_dir: Path,
    args: tuple[str, ...],
    on_progress: Callable[[str], None] | None = None,
    on_clone_start: Callable[[str, str, int], None] | None = None,
    on_item: Callable[[int, int, CloneItemResult], None] | None = None,
) -> DbtCloneRun:
    """Compile current and reuse manifests and clone selected dbt models."""

    options: DbtCloneOptions = parse_dbt_clone_options(args)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    enforce_dbt_interop_standard_mode(discovered_inputs=discovered_inputs)
    production_ref: DbtProductionRefConfig = discovered_inputs.project_config.dbt.production_ref
    if production_ref.git_ref is None or production_ref.generate_schema_name_override is None:
        raise DbtInteropConfigError(
            "dbt clone requires [dbt.production_ref] to be configured",
            code="C348",
            help=(
                "Run sqb dbt init or set [dbt.production_ref].git_ref and "
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
    _report_progress(
        on_progress, f"Compiling dbt production ref git ref '{production_ref.git_ref}'..."
    )
    production_ref_start: float = time.monotonic()
    production_ref_compile: DbtProductionRefCompileResult = compile_production_ref_manifest(
        sqlbuild_project_dir=project_dir,
        dbt_options=dbt_options,
        production_ref=production_ref,
        runner=runner,
    )
    reuse_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=json.loads(production_ref_compile.manifest_contents)
    )
    _report_progress(
        on_progress,
        f"Compiled dbt production ref git ref '{production_ref.git_ref}'. "
        f"({time.monotonic() - production_ref_start:.2f}s)",
    )
    _report_progress(on_progress, "Resolving dbt selection...")
    selected_nodes: tuple[DbtLsNode, ...] = _resolve_selected_nodes(
        runner=runner,
        dbt_options=dbt_options,
        options=options,
    )
    if not selected_nodes:
        raise DbtInteropConfigError(
            "dbt clone selected no dbt models",
            code="C349",
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
    origin_label: str = production_ref.git_ref
    destination_label: str = (
        dbt_options.target
        or discovered_inputs.local_config.target
        or discovered_inputs.project_config.default_target
        or "current"
    )
    try:
        _report_progress(on_progress, "Applying clone plan...")
        clone_start: float = time.monotonic()

        def _on_start(total: int) -> None:
            if on_clone_start is not None:
                on_clone_start(origin_label, destination_label, total)

        result: CloneExecutionResult = execute_dbt_clone(
            adapter=adapter,
            connection=connection,
            current_manifest=current_manifest,
            reuse_manifest=reuse_manifest,
            selected_nodes=selected_nodes,
            hard_copy=options.hard_copy,
            on_start=_on_start,
            on_item=on_item,
        )
        _report_progress(
            on_progress, f"Applied clone plan. ({time.monotonic() - clone_start:.2f}s)"
        )
    finally:
        adapter.close(connection)
    return DbtCloneRun(
        result=result,
        origin_label=origin_label,
        destination_label=destination_label,
    )


def _resolve_selected_nodes(
    *, runner: DbtRunner, dbt_options: DbtCliOptions, options: DbtCloneOptions
) -> tuple[DbtLsNode, ...]:
    ls_result: DbtLsResult = runner.ls(
        options=dbt_options,
        select=options.select,
        exclude=options.exclude,
        resource_types=(DbtSupportedResourceType.MODEL,),
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
