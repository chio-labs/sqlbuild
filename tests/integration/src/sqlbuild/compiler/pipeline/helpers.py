from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.operations.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult

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
        no_sql_validation=True,
        defer_to=defer_to,
        select=select,
        exclude=exclude,
        on_progress=on_progress,
        resolve_python_run_selectors=resolve_python_run_selectors,
    )


def validate_manifest_against_dbt_schema(manifest: dict[str, object]) -> None:
    """Validate a manifest dict against the dbt v12 JSON schema."""

    from jsonschema import Draft202012Validator

    schema: dict[str, Any] = json.loads(_SCHEMA_FIXTURE_PATH.read_text(encoding="utf-8"))
    validator: Any = Draft202012Validator(schema)
    errors: list[str] = [e.message for e in validator.iter_errors(manifest)]
    assert errors == [], f"Manifest schema validation errors: {errors}"
