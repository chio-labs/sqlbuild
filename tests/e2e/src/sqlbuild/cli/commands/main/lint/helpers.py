"""Helpers for lint command performance guards."""

from __future__ import annotations

from pathlib import Path

CLEAN_MODEL_SQL: str = """MODEL (
  materialized view,
  description "Synthetic lint benchmark model."
);

SELECT
  1 AS id
"""
DIRTY_MODEL_SQL: str = """MODEL (
  materialized view,
  description "Synthetic dirty lint benchmark model."
);

SELECT value
FROM items
WHERE value = NULL
"""
SKIPPED_FIX_MODEL_SQL: str = """MODEL (
  materialized view,
  description "Synthetic skipped-fix benchmark model."
);

SELECT id FROM items LIMIT 1
"""
CONFLICTING_FIX_MODEL_SQL: str = """MODEL (
  materialized view,
  description "Synthetic overlapping-fix benchmark model."
);

WITH first_unused AS (SELECT 1), second_unused AS (SELECT 2)
SELECT 3 AS id
"""


def write_lint_performance_project(*, project_dir: Path, model_count: int, model_sql: str) -> None:
    """Write a project whose cost scales primarily with model count."""

    models_dir: Path = project_dir / "models"
    models_dir.mkdir(parents=True)
    _ = (project_dir / "sqlbuild_project.toml").write_text(
        "\n".join(
            (
                'name = "lint_performance"',
                'adapter = "duckdb"',
                'default_target = "dev"',
                "",
                "[connection]",
                'database = ":memory:"',
                "",
                "[targets.dev]",
                'schema = "main"',
                "",
            )
        ),
        encoding="utf-8",
    )
    for index in range(model_count):
        _ = (models_dir / f"model_{index:05d}.sql").write_text(model_sql, encoding="utf-8")


def write_pathological_lint_project(*, project_dir: Path, predicate_count: int) -> None:
    """Write one valid model containing a long repeated predicate chain."""

    write_lint_performance_project(
        project_dir=project_dir,
        model_count=0,
        model_sql=CLEAN_MODEL_SQL,
    )
    predicate: str = " OR ".join(f"value = {index}" for index in range(predicate_count))
    _ = (project_dir / "models" / "pathological.sql").write_text(
        'MODEL (description "Pathological native lint benchmark.");\n'
        f"SELECT value FROM items WHERE {predicate}\n",
        encoding="utf-8",
    )
