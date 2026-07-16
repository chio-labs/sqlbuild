from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.load_macros import load_macros
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.manifest.main.build import build_manifest
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineOptions, CompilePipelineResult
from sqlbuild.runtime.contracts.models import ConnectionHooks

_SCHEMA_FIXTURE_PATH: Path = (
    Path(__file__).resolve().parents[5] / "fixtures" / "dbt_manifest_v12_schema.json"
)


def run_compile_pipeline_for_project(
    *,
    project_dir: Path,
    adapter: BaseAdapter,
    defer_to: str | None = None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    on_progress: Callable[[str], None] | None = None,
    resolve_python_run_selectors: bool = False,
) -> CompilePipelineResult:
    """Discover a project and run the real compile pipeline."""

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    return run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        options=CompilePipelineOptions(
            no_sql_validation=True,
            defer_to=defer_to,
            select=select,
            exclude=exclude,
            resolve_python_run_selectors=resolve_python_run_selectors,
        ),
        hooks=ConnectionHooks(on_progress=on_progress),
    )


def build_manifest_for_pipeline_result(
    *,
    project_dir: Path,
    result: CompilePipelineResult,
    project_name: str,
    adapter_type: str,
) -> dict[str, object]:
    """Build the manifest artifact from a compile pipeline result."""

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    return build_manifest(
        project=result.project,
        plan_output=result.plan_output,
        loaded_macros=load_macros(discovered_inputs.macro_files),
        project_name=project_name,
        adapter_type=adapter_type,
        upstream_deps=result.plan_output.upstream_deps,
        downstream_deps=result.plan_output.downstream_deps,
    )


def validate_manifest_against_dbt_schema(manifest: dict[str, object]) -> None:
    """Validate a manifest dict against the dbt v12 JSON schema."""

    from jsonschema import Draft202012Validator

    schema: dict[str, Any] = json.loads(_SCHEMA_FIXTURE_PATH.read_text(encoding="utf-8"))
    validator: Any = Draft202012Validator(schema)
    errors: list[str] = [e.message for e in validator.iter_errors(manifest)]
    assert errors == [], f"Manifest schema validation errors: {errors}"
