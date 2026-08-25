"""Helpers for compile command performance guard tests."""

from __future__ import annotations

import os
import signal
import time
from bisect import bisect_left
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import Any

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main

_DBT_SHAPED_SQL_SIZE_PROFILE: tuple[tuple[float, int], ...] = (
    (0.50, 1_800),
    (0.75, 4_500),
    (0.90, 8_000),
    (0.95, 12_500),
    (0.99, 20_000),
    (0.992, 50_000),
    (0.994, 175_000),
    (0.999, 265_000),
    (1.0, 522_000),
)


def run_advanced_compile_benchmark(
    *,
    project_dir: Path,
    model_count: int,
    expected_max_seconds: float,
    scan_event_lines_per_model: int = 0,
) -> float:
    skip_actions: dict[bool, Callable[[], None]] = {
        False: _continue_compile_benchmark,
        True: _skip_compile_benchmark,
    }
    skip_actions[os.environ.get("SQLBUILD_SKIP_PERFORMANCE_TESTS") == "1"]()

    write_advanced_compile_project(
        project_dir=project_dir,
        model_count=model_count,
        scan_event_lines_per_model=scan_event_lines_per_model,
    )
    return _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_max_seconds,
    )


def run_dbt_shaped_compile_benchmark(
    *,
    project_dir: Path,
    model_count: int,
    expected_max_seconds: float,
    expected_warm_max_seconds: float,
) -> tuple[float, float]:
    skip_actions: dict[bool, Callable[[], None]] = {
        False: _continue_compile_benchmark,
        True: _skip_compile_benchmark,
    }
    skip_actions[os.environ.get("SQLBUILD_SKIP_PERFORMANCE_TESTS") == "1"]()
    write_dbt_shaped_compile_project(project_dir=project_dir, model_count=model_count)
    cold_seconds: float = _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_max_seconds,
    )
    warm_seconds: float = _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_warm_max_seconds,
    )
    return cold_seconds, warm_seconds


def _run_compile_benchmark(*, project_dir: Path, expected_max_seconds: float) -> float:
    with _fail_after_seconds(expected_max_seconds):
        start: float = time.perf_counter()
        exit_code: int = main(
            [
                "--project-dir",
                str(project_dir),
                "--no-color",
                "compile",
            ]
        )
        elapsed_seconds: float = time.perf_counter() - start
    assert exit_code == 0
    return elapsed_seconds


def measure_model_sql_bytes(project_dir: Path) -> int:
    return sum(path.stat().st_size for path in (project_dir / "models").glob("*.sql"))


@contextmanager
def _fail_after_seconds(seconds: float) -> Iterator[None]:
    def _raise_timeout(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        raise TimeoutError(f"compile benchmark exceeded {seconds:.1f}s budget")

    previous_handler: Any = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)


def write_advanced_compile_project(
    *,
    project_dir: Path,
    model_count: int,
    scan_event_lines_per_model: int = 0,
) -> None:
    models_dir: Path = project_dir / "models"
    models_dir.mkdir(parents=True)
    _write_compile_project_config(project_dir)
    base_model_sql: str = _with_reference_scan_workload(
        sql=_base_model_sql(),
        model_index=0,
        scan_event_lines=scan_event_lines_per_model,
    )
    (models_dir / "model_00000.sql").write_text(base_model_sql, encoding="utf-8")
    for index in range(1, model_count):
        model_sql: str = _with_reference_scan_workload(
            sql=_chain_model_sql(index=index),
            model_index=index,
            scan_event_lines=scan_event_lines_per_model,
        )
        (models_dir / f"model_{index:05d}.sql").write_text(model_sql, encoding="utf-8")


def write_dbt_shaped_compile_project(*, project_dir: Path, model_count: int) -> None:
    models_dir: Path = project_dir / "models"
    models_dir.mkdir(parents=True)
    _write_compile_project_config(project_dir)
    base_model_sql: str = _with_base_generated_logic(
        sql=_base_model_sql(),
        target_bytes=_sql_size_target(model_index=0, model_count=model_count),
    )
    (models_dir / "model_00000.sql").write_text(base_model_sql, encoding="utf-8")
    for index in range(1, model_count):
        model_sql: str = _with_chain_generated_logic(
            sql=_chain_model_sql(index=index),
            target_bytes=_sql_size_target(model_index=index, model_count=model_count),
        )
        (models_dir / f"model_{index:05d}.sql").write_text(model_sql, encoding="utf-8")


def _write_compile_project_config(project_dir: Path) -> None:
    (project_dir / "sqlbuild_project.toml").write_text(
        "\n".join(
            (
                'name = "performance_guard"',
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


def _continue_compile_benchmark() -> None:
    return None


def _skip_compile_benchmark() -> None:
    pytest.skip("SQLBUILD_SKIP_PERFORMANCE_TESTS=1")


def _with_reference_scan_workload(*, sql: str, model_index: int, scan_event_lines: int) -> str:
    comments: str = "".join(
        f"-- generated mapping {line:05d}: source='source_{model_index:05d}' "
        f"expression=__not_a_reference_{line:05d}\n"
        for line in range(scan_event_lines)
    )
    header_end: int = sql.index(";\n") + 2
    return f"{sql[:header_end]}{comments}{sql[header_end:]}"


def _sql_size_target(*, model_index: int, model_count: int) -> int:
    quantile: float = (model_index + 1) / model_count
    upper_quantiles: tuple[float, ...] = tuple(item[0] for item in _DBT_SHAPED_SQL_SIZE_PROFILE)
    target_sizes: tuple[int, ...] = tuple(item[1] for item in _DBT_SHAPED_SQL_SIZE_PROFILE)
    return target_sizes[bisect_left(upper_quantiles, quantile)]


def _generated_case_logic(*, sql: str, target_bytes: int) -> str:
    missing_bytes: int = max(0, target_bytes - len(sql.encode("utf-8")))
    clause_template: str = "      WHEN id = 00000 THEN 'segment_00000'\n"
    clause_count: int = (missing_bytes + len(clause_template) - 1) // len(clause_template)
    clauses: str = "".join(
        f"      WHEN id = {index:05d} THEN 'segment_{index:05d}'\n" for index in range(clause_count)
    )
    return f"    CASE\n{clauses}      ELSE 'unmatched'\n    END AS generated_mapping"


def _with_base_generated_logic(*, sql: str, target_bytes: int) -> str:
    header, query = sql.split(";\n", 1)
    generated_logic: str = _generated_case_logic(sql=sql, target_bytes=target_bytes)
    return f"""{header};
WITH base AS (
{query.rstrip()}
),
generated_logic AS (
  SELECT
    *,
{generated_logic}
  FROM base
)
SELECT id, bucket, amount, avg_amount, max_amount, status
FROM generated_logic
"""


def _with_chain_generated_logic(*, sql: str, target_bytes: int) -> str:
    generated_logic: str = _generated_case_logic(sql=sql, target_bytes=target_bytes)
    widened_sql: str = sql.replace(
        ")\nSELECT\n  id,",
        f"""),
generated_logic AS (
  SELECT
    *,
{generated_logic}
  FROM joined
)
SELECT
  id,""",
        1,
    )
    prefix, suffix = widened_sql.rsplit("\nFROM joined", 1)
    return f"{prefix}\nFROM generated_logic{suffix}"


def _base_model_sql() -> str:
    return "\n".join(
        (
            "MODEL (materialized view);",
            "",
            "SELECT",
            "  0 AS id,",
            "  'even' AS bucket,",
            "  CAST(1 AS DOUBLE) AS amount,",
            "  CAST(1 AS DOUBLE) AS avg_amount,",
            "  CAST(1 AS DOUBLE) AS max_amount,",
            "  'small' AS status",
            "",
        )
    )


def _chain_model_sql(*, index: int) -> str:
    previous_model: str = f"model_{index - 1:05d}"
    return f'''MODEL (materialized view);

WITH base AS (
  SELECT
    id + 1 AS id,
    bucket,
    CAST(amount AS DOUBLE) AS amount,
    CAST(avg_amount AS DOUBLE) AS avg_amount,
    CAST(max_amount AS DOUBLE) AS max_amount,
    status
  FROM __ref("{previous_model}")
),
windowed AS (
  SELECT
    id,
    CASE WHEN id % 2 = 0 THEN 'even' ELSE 'odd' END AS bucket,
    amount + avg_amount AS amount,
    LAG(amount, 1, 0) OVER (ORDER BY id) AS previous_amount,
    SUM(amount) OVER (
      PARTITION BY bucket
      ORDER BY id
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_amount,
    ROW_NUMBER() OVER (PARTITION BY bucket ORDER BY id) AS row_number
  FROM base
),
grouped AS (
  SELECT
    bucket,
    AVG(amount) AS avg_amount,
    MAX(running_amount) AS max_amount,
    COUNT(*) AS row_count
  FROM windowed
  GROUP BY bucket
),
joined AS (
  SELECT
    w.id,
    w.bucket,
    w.amount + COALESCE(w.previous_amount, 0) AS amount,
    g.avg_amount,
    g.max_amount,
    CASE
      WHEN g.row_count > 10 THEN 'large'
      WHEN w.amount > g.avg_amount THEN 'above_average'
      ELSE 'small'
    END AS status
  FROM windowed w
  JOIN grouped g
    ON w.bucket = g.bucket
  WHERE w.row_number >= 1
)
SELECT
  id,
  bucket,
  amount,
  avg_amount,
  max_amount,
  status
FROM joined
'''
