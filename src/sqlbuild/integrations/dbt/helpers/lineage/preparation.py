"""Preparation of compiled dbt/SQLBuild inputs for lineage commands."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.integrations.dbt.classes.dbt_compile_reference_resolver import (
    DbtCompileReferenceResolver,
)
from sqlbuild.integrations.dbt.classes.dbt_runner import DbtRunner
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.cli.mode import enforce_dbt_interop_standard_mode
from sqlbuild.integrations.dbt.helpers.graph.core import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.lineage.args import parse_dbt_lineage_args
from sqlbuild.integrations.dbt.helpers.manifest.core import load_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.planning.runtime import (
    resolve_dbt_interop_adapter,
    resolve_dbt_manifest_path,
    resolve_dbt_plan_options,
)
from sqlbuild.integrations.dbt.helpers.profile.connection import resolve_connection_config
from sqlbuild.integrations.dbt.helpers.runtime.progress import report_progress
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtLineageArgs,
    DbtLineagePreparation,
)
from sqlbuild.spec.resolution.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def prepare_dbt_lineage_inputs(
    *,
    project_dir: Path,
    args: tuple[str, ...],
    on_progress: Callable[[str], None] | None,
) -> DbtLineagePreparation:
    """Compile the dbt project and assemble the combined lineage inputs."""

    lineage_args: DbtLineageArgs = parse_dbt_lineage_args(args)
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    enforce_dbt_interop_standard_mode(discovered_inputs=discovered_inputs)
    dbt_options: DbtCliOptions = resolve_dbt_plan_options(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        dbt_args=lineage_args.dbt_args,
    )
    runner: DbtRunner = DbtRunner()
    report_progress(on_progress=on_progress, message="Compiling dbt project...")
    dbt_compile_start: float = time.monotonic()
    compile_result: DbtCommandResult = runner.compile(options=dbt_options)
    if compile_result.returncode != 0:
        raise DbtInteropRuntimeError(
            "dbt compile failed",
            help=compile_result.stderr or compile_result.stdout,
        )
    report_progress(
        on_progress=on_progress,
        message=f"Compiled dbt project. ({time.monotonic() - dbt_compile_start:.2f}s)",
    )
    report_progress(on_progress=on_progress, message="Loading dbt manifest...")
    manifest: DbtManifestIndex = load_dbt_manifest_index(
        manifest_path=resolve_dbt_manifest_path(options=dbt_options)
    )
    report_progress(on_progress=on_progress, message="Loaded dbt manifest.")
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_dbt_interop_adapter(
        adapter_name=adapter_name, project_dir=project_dir
    )
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=lineage_args.no_sql_validation,
        external_sql_reference_resolver=DbtCompileReferenceResolver(dbt_manifest=manifest),
    )
    return DbtLineagePreparation(
        lineage_args=lineage_args,
        manifest=manifest,
        adapter=adapter,
        project=project,
        graph=build_dbt_combined_graph(manifest=manifest, project=project),
        connection_config=resolve_connection_config(
            raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
            project_dir=project_dir,
            adapter_name=adapter_name,
            discovered_inputs=discovered_inputs,
        ),
    )
