"""Generated project helpers for format performance guards."""

from __future__ import annotations

from pathlib import Path


def write_format_performance_project(
    *, project_dir: Path, model_count: int, test_count: int
) -> None:
    """Write a deterministic contract-heavy project with unique SQL test fixtures."""

    project_dir.mkdir()
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "format_guard"\nadapter = "duckdb"\n[defaults]\ncontract = "enforced"\n',
        encoding="utf-8",
    )
    models_dir: Path = project_dir / "models"
    tests_dir: Path = project_dir / "tests" / "unit" / "orders"
    models_dir.mkdir()
    tests_dir.mkdir(parents=True)
    for model_index in range(model_count):
        models_dir.joinpath(f"orders_{model_index:05d}.sql").write_text(
            "MODEL (columns (order_id (type INTEGER), note (type VARCHAR)));\n"
            f"SELECT {model_index} AS order_id, 'ready' AS note\n",
            encoding="utf-8",
        )
    for test_index in range(test_count):
        model_index: int = test_index % model_count
        tests_dir.joinpath(f"test_orders_{test_index:05d}.sql").write_text(
            "TEST();\n\n"
            f"WITH __ref__orders_{model_index:05d} AS (\n"
            "  SELECT\n"
            f"    {test_index} AS order_id,\n"
            "    CAST(NULL AS VARCHAR) AS note\n"
            f"), __expected__orders_{model_index:05d} AS (\n"
            f"  SELECT {test_index} AS order_id, NULL AS note\n"
            ")\n"
            "SELECT 1\n",
            encoding="utf-8",
        )


def count_typed_null_candidates(*, project_dir: Path) -> int:
    """Count generated typed-null projections before or after a check-only run."""

    return sum(
        path.read_text(encoding="utf-8").count("CAST(NULL AS VARCHAR)")
        for path in (project_dir / "tests").rglob("*.sql")
    )
