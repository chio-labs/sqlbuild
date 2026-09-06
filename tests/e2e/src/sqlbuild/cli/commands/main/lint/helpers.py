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


def write_varied_production_lint_project(*, project_dir: Path, model_count: int) -> None:
    """Write varied multi-CTE SQL so native response deduplication cannot hide scaling."""

    write_lint_performance_project(
        project_dir=project_dir,
        model_count=0,
        model_sql=CLEAN_MODEL_SQL,
    )
    models_dir: Path = project_dir / "models"
    for index in range(model_count):
        ctes: list[str] = [
            "stage_00 AS (\n"
            f"  SELECT {index} AS benchmark_id, id, COALESCE(value, 0) AS normalized_value\n"
            "  FROM benchmark_source\n"
            ")"
        ]
        for stage in range(1, 25):
            previous: str = f"stage_{stage - 1:02d}"
            ctes.append(
                f"stage_{stage:02d} AS (\n"
                "  SELECT benchmark_id, id, normalized_value,\n"
                "    ROW_NUMBER() OVER (PARTITION BY benchmark_id ORDER BY id) AS row_number\n"
                f"  FROM {previous}\n"
                ")"
            )
        sql: str = (
            'MODEL (description "Varied production-shaped lint benchmark.");\n'
            "WITH " + ",\n".join(ctes) + "\nSELECT benchmark_id, id, normalized_value\n"
            "FROM stage_24\n"
            "WHERE row_number = 1\n"
            "ORDER BY benchmark_id, id\n"
        )
        _ = (models_dir / f"model_{index:05d}.sql").write_text(sql, encoding="utf-8")


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
