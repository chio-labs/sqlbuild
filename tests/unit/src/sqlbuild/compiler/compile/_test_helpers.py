from pathlib import Path

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


def build_external_reference_resolver(*, project_dir: Path) -> ExternalReferenceResolver | None:
    manifest_path: Path = project_dir / "dbt" / "target" / "manifest.json"
    if not manifest_path.is_file():
        return None
    return build_compile_reference_resolver(
        manifest_contents=manifest_path.read_text(encoding="utf-8")
    )


def expected_or_actual[T](expected: T | None, actual: T) -> T:
    if expected is None:
        return actual
    return expected
