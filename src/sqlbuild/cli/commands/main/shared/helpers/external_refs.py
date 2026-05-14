"""CLI helpers for optional external SQL reference integrations."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.main.build_compile_reference_resolver import (
    build_compile_reference_resolver,
)
from sqlbuild.shared.types import ExternalSqlReferenceResolver


def resolve_external_sql_reference_resolver(
    *, project_dir: Path, discovered_inputs: DiscoveredProjectInputs
) -> ExternalSqlReferenceResolver | None:
    """Build the external reference resolver configured for a discovered project."""

    manifest_contents: str | None = _read_dbt_manifest_contents(
        project_dir=project_dir,
        target_path=discovered_inputs.project_config.dbt.target_path,
    )
    return build_compile_reference_resolver(
        manifest_contents=manifest_contents,
    )


def _read_dbt_manifest_contents(*, project_dir: Path, target_path: str | None) -> str | None:
    if target_path is None:
        return None
    raw_target_path: Path = Path(target_path)
    resolved_target_path: Path = (
        raw_target_path if raw_target_path.is_absolute() else project_dir / raw_target_path
    )
    manifest_path: Path = resolved_target_path / "manifest.json"
    if not manifest_path.is_file():
        return None
    return manifest_path.read_text(encoding="utf-8")
