from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredDbtManifestFile, DiscoveredProjectInputs
from sqlbuild.integrations.dbt.main.build_compile_reference_resolver import (
    build_compile_reference_resolver,
)
from sqlbuild.shared.types import ExternalReferenceResolver


def base_repo_files() -> dict[str, str]:
    return {
        "sqlbuild_project.toml": (
            'name = "demo"\nadapter = "duckdb"\n\n[settings]\ndefault_audit_severity = "warn"\n'
        ),
    }


def attach_dbt_manifest_file(
    *, discovered_inputs: DiscoveredProjectInputs, project_dir: Path
) -> DiscoveredProjectInputs:
    manifest_path: Path = project_dir / "dbt" / "target" / "manifest.json"
    if not manifest_path.is_file():
        return discovered_inputs
    return replace(
        discovered_inputs,
        dbt_manifest_file=DiscoveredDbtManifestFile(
            file_path=manifest_path,
            relative_path=manifest_path.relative_to(project_dir),
            contents=manifest_path.read_text(encoding="utf-8"),
        ),
    )


def build_external_reference_resolver(
    discovered_inputs: DiscoveredProjectInputs,
) -> ExternalReferenceResolver | None:
    return build_compile_reference_resolver(
        manifest_contents=(
            None
            if discovered_inputs.dbt_manifest_file is None
            else discovered_inputs.dbt_manifest_file.contents
        )
    )


def expected_or_actual[T](expected: T | None, actual: T) -> T:
    if expected is None:
        return actual
    return expected
