from __future__ import annotations

from pathlib import Path


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
