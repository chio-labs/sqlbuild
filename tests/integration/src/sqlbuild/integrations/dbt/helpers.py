from __future__ import annotations

import subprocess
from pathlib import Path

from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.integrations.dbt.main.manifest.build_compile_reference_resolver import (
    build_compile_reference_resolver,
)


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


def build_external_sql_reference_resolver(
    *, manifest_source: Path
) -> ExternalSqlReferenceResolver | None:
    """Build a dbt-backed resolver for attached manifest integration tests."""

    return build_compile_reference_resolver(
        manifest_contents=manifest_source.read_text(encoding="utf-8")
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

    resolved_argvs: list[tuple[str, ...]] = []
    for argv in argvs:
        resolved_argv: list[str] = []
        for value in argv:
            resolved_argv.append(
                value.format(
                    dbt_project_dir=dbt_project_dir,
                    dbt_profiles_dir=dbt_profiles_dir,
                    dbt_target_path=dbt_target_path,
                )
            )
        resolved_argvs.append(tuple(resolved_argv))
    return tuple(resolved_argvs)


def run_git_command(*, repo_dir: Path, args: tuple[str, ...]) -> None:
    """Run one git command for local integration-test repositories."""

    result: subprocess.CompletedProcess[str] = subprocess.run(
        ("git", *args),
        cwd=repo_dir,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)


def count_available_reuse_refs(*, help_text: str) -> int:
    """Count refs in a dbt reuse invalid-ref help message."""

    marker: str = "Available local branches/tags include: "
    if marker not in help_text:
        return 0
    available_refs: str = help_text.split(marker, 1)[1]
    return len(available_refs.removesuffix(".").split(", "))


def set_git_identity(*, repo_dir: Path) -> None:
    """Configure repo-local git identity for test commits."""

    run_git_command(repo_dir=repo_dir, args=("config", "user.email", "test@example.com"))
    run_git_command(repo_dir=repo_dir, args=("config", "user.name", "Test User"))


def build_local_production_ref_git_project(*, tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Create a local git repo with SQLBuild and dbt projects for production_ref tests."""

    repo_dir: Path = tmp_path / "repo"
    sqlbuild_project_dir: Path = repo_dir / "sqlbuild_project"
    dbt_project_dir: Path = repo_dir / "dbt_project"
    profiles_dir: Path = tmp_path / "profiles"
    macro_relative_path: Path = Path("dbt/macros/prod_generate_schema_name.sql")
    macro_path: Path = sqlbuild_project_dir / macro_relative_path
    dbt_models_dir: Path = dbt_project_dir / "models"

    repo_dir.mkdir()
    macro_path.parent.mkdir(parents=True)
    dbt_models_dir.mkdir(parents=True)
    profiles_dir.mkdir()
    sqlbuild_project_dir.joinpath("sqlbuild_project.toml").write_text(
        'name = "demo"\nadapter = "duckdb"\n',
        encoding="utf-8",
    )
    macro_path.write_text(
        "\n".join(
            (
                "{% macro generate_schema_name(custom_schema_name, node) %}",
                "{{ 'prod_' ~ target.schema }}",
                "{% endmacro %}",
            )
        ),
        encoding="utf-8",
    )
    dbt_project_dir.joinpath("dbt_project.yml").write_text(
        "\n".join(
            (
                'name: "analytics"',
                'version: "1.0"',
                'profile: "analytics"',
                'model-paths: ["models"]',
                "models:",
                "  analytics:",
                "    +materialized: view",
            )
        ),
        encoding="utf-8",
    )
    dbt_models_dir.joinpath("stg_orders.sql").write_text(
        "select 1 as order_id\n",
        encoding="utf-8",
    )
    profiles_dir.joinpath("profiles.yml").write_text(
        "\n".join(
            (
                "analytics:",
                "  target: dev",
                "  outputs:",
                "    dev:",
                "      type: duckdb",
                "      path: ':memory:'",
                "      schema: dev",
            )
        ),
        encoding="utf-8",
    )
    run_git_command(repo_dir=repo_dir, args=("init", "--initial-branch", "main"))
    set_git_identity(repo_dir=repo_dir)
    run_git_command(repo_dir=repo_dir, args=("add", "."))
    run_git_command(repo_dir=repo_dir, args=("commit", "-m", "prod dbt project"))
    run_git_command(repo_dir=repo_dir, args=("branch", "prod"))
    dbt_models_dir.joinpath("stg_orders.sql").write_text(
        "select 2 as order_id\n",
        encoding="utf-8",
    )
    return sqlbuild_project_dir, dbt_project_dir, profiles_dir, macro_relative_path
