"""Helpers for compile command performance guard tests."""

from __future__ import annotations

import os
import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import Any

import pytest

from sqlbuild.cli.commands.main.entry import main


def run_advanced_compile_benchmark(
    *, project_dir: Path, model_count: int, expected_max_seconds: float
) -> float:
    if os.environ.get("SQLBUILD_SKIP_PERFORMANCE_TESTS") == "1":
        pytest.skip("SQLBUILD_SKIP_PERFORMANCE_TESTS=1")

    _write_advanced_compile_project(project_dir=project_dir, model_count=model_count)
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


def _write_advanced_compile_project(*, project_dir: Path, model_count: int) -> None:
    models_dir: Path = project_dir / "models"
    models_dir.mkdir(parents=True)
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
    for index in range(model_count):
        model_sql: str = _base_model_sql() if index == 0 else _chain_model_sql(index=index)
        (models_dir / f"model_{index:05d}.sql").write_text(model_sql, encoding="utf-8")


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
