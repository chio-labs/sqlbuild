from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredDbtManifestFile, DiscoveredProjectInputs
from sqlbuild.integrations.dbt.main.build_compile_reference_resolver import (
    build_compile_reference_resolver,
)
from sqlbuild.shared.types import ExternalReferenceResolver


def build_sqlbuild_project_with_manifest(
    *, tmp_path: Path, manifest_source: Path, model_sql_by_name: dict[str, str]
) -> Path:
    """Create a tiny SQLBuild project with a copied dbt manifest."""

    project_dir: Path = tmp_path / "sqlbuild_project"
    project_dir.joinpath("models").mkdir(parents=True)
    project_dir.joinpath("target").mkdir()
    project_dir.joinpath("sqlbuild_project.toml").write_text(
        'name = "demo"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model_name: str
    sql: str
    for model_name, sql in model_sql_by_name.items():
        project_dir.joinpath(f"models/{model_name}.sql").write_text(
            f"MODEL ();\n\n{sql}\n", encoding="utf-8"
        )
    project_dir.joinpath("target/manifest.json").write_text(
        manifest_source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return project_dir


def attach_dbt_manifest_file(
    *, discovered_inputs: DiscoveredProjectInputs, manifest_source: Path
) -> DiscoveredProjectInputs:
    """Attach a dbt manifest explicitly for dbt interop integration tests."""

    return replace(
        discovered_inputs,
        dbt_manifest_file=DiscoveredDbtManifestFile(
            file_path=manifest_source,
            relative_path=Path("manifest.json"),
            contents=manifest_source.read_text(encoding="utf-8"),
        ),
    )


def build_external_reference_resolver(
    discovered_inputs: DiscoveredProjectInputs,
) -> ExternalReferenceResolver | None:
    """Build a dbt-backed resolver for attached manifest integration tests."""

    return build_compile_reference_resolver(
        manifest_contents=(
            None
            if discovered_inputs.dbt_manifest_file is None
            else discovered_inputs.dbt_manifest_file.contents
        )
    )


def build_sqlbuild_project_with_dbt_config(
    *,
    tmp_path: Path,
    dbt_project_dir: Path,
    dbt_profiles_dir: Path,
    dbt_target_path: Path,
    model_sql_by_relative_path: dict[str, str],
) -> Path:
    """Create a tiny SQLBuild project configured for real dbt interop planning."""

    project_dir: Path = tmp_path / "sqlbuild_plan_project"
    project_dir.joinpath("models").mkdir(parents=True)
    project_dir.joinpath("sqlbuild_project.toml").write_text(
        "\n".join(
            (
                'name = "demo"',
                'adapter = "duckdb"',
                "",
                "[connection]",
                'database = "demo.duckdb"',
                "",
                "[dbt]",
                f'project_dir = "{dbt_project_dir.as_posix()}"',
                f'profiles_dir = "{dbt_profiles_dir.as_posix()}"',
                f'target_path = "{dbt_target_path.as_posix()}"',
            )
        ),
        encoding="utf-8",
    )
    relative_path: str
    sql: str
    for relative_path, sql in model_sql_by_relative_path.items():
        model_path: Path = project_dir / "models" / relative_path
        model_path.parent.mkdir(parents=True, exist_ok=True)
        contents: str = sql if sql.lstrip().startswith("MODEL ") else f"MODEL ();\n\n{sql}\n"
        model_path.write_text(contents, encoding="utf-8")
    return project_dir


def resolve_expected_dbt_argvs(
    argvs: tuple[tuple[str, ...], ...],
    *,
    dbt_project_dir: Path,
    dbt_profiles_dir: Path,
    dbt_target_path: Path,
) -> tuple[tuple[str, ...], ...]:
    """Replace path placeholders in expected dbt argv tuples."""

    return tuple(
        tuple(
            value.format(
                dbt_project_dir=dbt_project_dir,
                dbt_profiles_dir=dbt_profiles_dir,
                dbt_target_path=dbt_target_path,
            )
            for value in argv
        )
        for argv in argvs
    )
