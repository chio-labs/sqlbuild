"""Write the dense synthetic project for delta compile series, on DuckDB by default."""

from __future__ import annotations

from pathlib import Path

from scripts.cold_compile_performance._helpers.dense_project import write_dense_compile_project
from scripts.delta_compile_series.constants import PROJECT_CONFIG


def write_delta_compile_project(
    *, project_dir: Path, model_count: int, adapter: str = "duckdb"
) -> None:
    """Write sources, seeds, functions, macros, models, SQL tests and custom rules on `adapter`."""

    write_dense_compile_project(project_dir=project_dir, model_count=model_count)
    config: Path = project_dir / PROJECT_CONFIG
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            'adapter = "snowflake"', f'adapter = "{adapter}"'
        ),
        encoding="utf-8",
    )
