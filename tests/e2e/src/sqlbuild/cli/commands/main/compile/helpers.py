"""Helpers for compile command performance guard tests."""

from __future__ import annotations

import json
import os
import signal
import time
from bisect import bisect_left
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from types import FrameType
from typing import Any, NamedTuple

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


class CompileBenchmarkMeasurement(NamedTuple):
    elapsed_seconds: float
    timings_ms: dict[str, int]
    summary: dict[str, int]


class DagsterShapedCompileBenchmarkResult(NamedTuple):
    cold: CompileBenchmarkMeasurement
    warm: CompileBenchmarkMeasurement
    leaf_model_edit: CompileBenchmarkMeasurement
    central_model_edit: CompileBenchmarkMeasurement
    test_edit: CompileBenchmarkMeasurement
    macro_edit: CompileBenchmarkMeasurement
    project_config_edit: CompileBenchmarkMeasurement


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


def run_test_heavy_compile_benchmark(
    *,
    project_dir: Path,
    model_count: int,
    test_count: int,
    chain_depth: int,
    fixture_row_count: int,
    expected_max_seconds: float,
    expected_warm_max_seconds: float,
    expected_edit_max_seconds: float,
) -> tuple[float, float, float, float]:
    skip_actions: dict[bool, Callable[[], None]] = {
        False: _continue_compile_benchmark,
        True: _skip_compile_benchmark,
    }
    skip_actions[os.environ.get("SQLBUILD_SKIP_PERFORMANCE_TESTS") == "1"]()
    write_test_heavy_compile_project(
        project_dir=project_dir,
        model_count=model_count,
        test_count=test_count,
        chain_depth=chain_depth,
        fixture_row_count=fixture_row_count,
    )
    cold_seconds: float = _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_max_seconds,
    )
    warm_seconds: float = _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_warm_max_seconds,
    )
    _append_benchmark_edit(project_dir / "models" / "model_00000.sql", "model")
    model_edit_seconds: float = _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_edit_max_seconds,
    )
    _append_benchmark_edit(project_dir / "tests" / "unit" / "test_00000.sql", "test")
    test_edit_seconds: float = _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_edit_max_seconds,
    )
    return cold_seconds, warm_seconds, model_edit_seconds, test_edit_seconds


def run_dagster_shaped_compile_benchmark(
    *,
    project_dir: Path,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
    test_count: int,
    expected_cold_max_seconds: float,
    expected_warm_max_seconds: float,
    expected_edit_max_seconds: float,
    expected_config_edit_max_seconds: float,
) -> DagsterShapedCompileBenchmarkResult:
    """Measure the production-shaped cold, warm, and representative edit paths."""

    skip_actions: dict[bool, Callable[[], None]] = {
        False: _continue_compile_benchmark,
        True: _skip_compile_benchmark,
    }
    skip_actions[os.environ.get("SQLBUILD_SKIP_PERFORMANCE_TESTS") == "1"]()
    warmup_dir: Path = project_dir.parent / "compile_runtime_warmup"
    write_advanced_compile_project(project_dir=warmup_dir, model_count=32)
    _ = _run_compile_benchmark(project_dir=warmup_dir, expected_max_seconds=5.0)
    write_dagster_shaped_compile_project(
        project_dir=project_dir,
        model_count=model_count,
        source_count=source_count,
        seed_count=seed_count,
        function_count=function_count,
        macro_count=macro_count,
        test_count=test_count,
    )
    cold: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_cold_max_seconds,
    )
    warm: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_warm_max_seconds,
    )
    _append_benchmark_edit(_generated_model_path(project_dir, model_count - 1), "leaf model")
    leaf_model_edit: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_edit_max_seconds,
    )
    _append_benchmark_edit(_generated_model_path(project_dir, 0), "central model")
    central_model_edit: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_edit_max_seconds,
    )
    _append_benchmark_edit(
        project_dir / "tests" / "unit" / "test_group_00000.sql",
        "test",
    )
    test_edit: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_edit_max_seconds,
    )
    macro_path: Path = project_dir / "models" / "macros" / "macro_00000.py"
    _replace_benchmark_text(
        path=macro_path,
        old='return f"({expression} + 0)"',
        new='return f"({expression} + 1000)"',
    )
    macro_edit: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_edit_max_seconds,
    )
    config_path: Path = project_dir / "sqlbuild_project.toml"
    _replace_benchmark_text(
        path=config_path,
        old='benchmark_revision = "0"',
        new='benchmark_revision = "1"',
    )
    project_config_edit: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_config_edit_max_seconds,
    )
    return DagsterShapedCompileBenchmarkResult(
        cold=cold,
        warm=warm,
        leaf_model_edit=leaf_model_edit,
        central_model_edit=central_model_edit,
        test_edit=test_edit,
        macro_edit=macro_edit,
        project_config_edit=project_config_edit,
    )


def _append_benchmark_edit(path: Path, label: str) -> None:
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n-- one {label} edit\n",
        encoding="utf-8",
    )


def _replace_benchmark_text(*, path: Path, old: str, new: str) -> None:
    contents: str = path.read_text(encoding="utf-8")
    _ = contents.index(old)
    path.write_text(contents.replace(old, new, 1), encoding="utf-8")


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


def _run_profiled_compile_benchmark(
    *, project_dir: Path, expected_max_seconds: float
) -> CompileBenchmarkMeasurement:
    output: StringIO = StringIO()
    diagnostic_grace_seconds: float = 5.0
    with (
        _fail_after_seconds(expected_max_seconds + diagnostic_grace_seconds),
        redirect_stdout(output),
    ):
        start: float = time.perf_counter()
        exit_code: int = main(
            [
                "--project-dir",
                str(project_dir),
                "--no-color",
                "compile",
                "--json",
            ]
        )
        elapsed_seconds: float = time.perf_counter() - start
    assert exit_code == 0
    payload: dict[str, object] = json.loads(output.getvalue())
    timings: object = payload["compile_timings"]
    summary: object = payload["summary"]
    assert isinstance(timings, dict)
    assert isinstance(summary, dict)
    return CompileBenchmarkMeasurement(
        elapsed_seconds=elapsed_seconds,
        timings_ms={str(key): int(value) for key, value in timings.items()},
        summary={str(key): int(value) for key, value in summary.items()},
    )


def _generated_model_path(project_dir: Path, index: int) -> Path:
    layer_index: int = index % 10
    folder: str = {
        (True, True): "staging",
        (False, True): "intermediate",
        (False, False): "mart",
    }[(layer_index < 4, layer_index < 8)]
    return project_dir / "models" / folder / f"model_{index:05d}.sql"


def measure_model_sql_bytes(project_dir: Path) -> int:
    return sum(path.stat().st_size for path in (project_dir / "models").rglob("*.sql"))


def measure_compiled_test_sql_bytes(project_dir: Path) -> int:
    compiled_tests_dir: Path = project_dir / "target" / "compiled" / "tests"
    return sum(path.stat().st_size for path in compiled_tests_dir.rglob("*.sql"))


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


def write_test_heavy_compile_project(
    *,
    project_dir: Path,
    model_count: int,
    test_count: int,
    chain_depth: int,
    fixture_row_count: int,
) -> None:
    models_dir: Path = project_dir / "models"
    tests_dir: Path = project_dir / "tests" / "unit"
    models_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)
    _write_compile_project_config(project_dir)
    for index in range(model_count):
        group_offset: int = index % chain_depth
        model_sql_builder: Callable[..., str] = {
            True: _test_heavy_base_model_sql,
            False: _test_heavy_chain_model_sql,
        }[group_offset == 0]
        model_sql: str = model_sql_builder(index=index)
        (models_dir / f"model_{index:05d}.sql").write_text(model_sql, encoding="utf-8")
    group_count: int = model_count // chain_depth
    for test_index in range(test_count):
        cases_per_target: int = 5
        group_index: int = (test_index // cases_per_target) % group_count
        base_index: int = group_index * chain_depth
        target_index: int = base_index + chain_depth - 1
        test_sql: str = _test_heavy_sql(
            base_index=base_index,
            target_index=target_index,
            fixture_row_count=fixture_row_count,
        )
        (tests_dir / f"test_{test_index:05d}.sql").write_text(test_sql, encoding="utf-8")


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


def _test_heavy_base_model_sql(*, index: int) -> str:
    return f"""MODEL (materialized view);

SELECT
  {index} AS id,
  CAST({index} AS DOUBLE) AS amount,
  'base' AS status
"""


def _test_heavy_chain_model_sql(*, index: int) -> str:
    previous_model: str = f"model_{index - 1:05d}"
    return f'''MODEL (materialized view);

WITH transformed AS (
  SELECT
    id + 1 AS id,
    amount + {index} AS amount,
    CASE WHEN id % 2 = 0 THEN 'even' ELSE 'odd' END AS status
  FROM __ref("{previous_model}")
),
windowed AS (
  SELECT
    id,
    amount,
    status,
    ROW_NUMBER() OVER (PARTITION BY status ORDER BY id) AS row_number,
    SUM(amount) OVER (PARTITION BY status ORDER BY id) AS running_amount
  FROM transformed
)
SELECT id, amount + running_amount AS amount, status
FROM windowed
WHERE row_number >= 1
'''


def _test_heavy_sql(*, base_index: int, target_index: int, fixture_row_count: int) -> str:
    fixture_rows: str = " UNION ALL\n".join(
        f"  SELECT {row} AS id, CAST({row} AS DOUBLE) AS amount, 'base' AS status"
        for row in range(fixture_row_count)
    )
    return f"""TEST();

WITH
__ref__model_{base_index:05d} AS (
{fixture_rows}
),
__expected__model_{target_index:05d} AS (
  SELECT 1 AS id, CAST(1 AS DOUBLE) AS amount, 'odd' AS status
)
SELECT 1
"""


_SPINE_DEPTH: int = 54
_TEST_CHAIN_DEPTH: int = 8
_ATTACHED_AUDIT_COUNT: int = 700
_TOP_LEVEL_WITH_INTERVAL: int = 20
_NESTED_QUERY_INTERVAL: int = 15
_MACRO_INTERVAL: int = 13
_FUNCTION_INTERVAL: int = 43
_SEED_INTERVAL: int = 67
_SEED_REFERENCE_START_INDEX: int = 300
_SQL_SIZE_PROFILE: tuple[tuple[float, int], ...] = (
    (0.0, 400),
    (0.50, 1_900),
    (0.75, 4_500),
    (0.90, 11_000),
    (0.95, 15_200),
    (0.99, 48_200),
    (0.995, 120_000),
    (0.999, 260_000),
    (1.0, 520_000),
)


def write_dagster_shaped_compile_project(
    *,
    project_dir: Path,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
    test_count: int,
) -> None:
    """Write a deterministic generated project matching real resource ratios."""

    _dagster_write_project_config(project_dir=project_dir)
    _dagster_write_sources(project_dir=project_dir, source_count=source_count)
    _dagster_write_seeds(project_dir=project_dir, seed_count=seed_count)
    _dagster_write_functions(project_dir=project_dir, function_count=function_count)
    _dagster_write_macros(project_dir=project_dir, macro_count=macro_count)
    _dagster_write_schemas(project_dir=project_dir)
    _dagster_write_hooks(project_dir=project_dir)
    _dagster_write_models(
        project_dir=project_dir,
        model_count=model_count,
        source_count=source_count,
        seed_count=seed_count,
        function_count=function_count,
        macro_count=macro_count,
    )
    _dagster_write_tests(
        project_dir=project_dir,
        model_count=model_count,
        test_count=test_count,
        source_count=source_count,
    )


def _dagster_write_project_config(*, project_dir: Path) -> None:
    project_dir.mkdir(parents=True)
    (project_dir / "sqlbuild_project.toml").write_text(
        """name = "dagster_shaped_performance_guard"
adapter = "duckdb"
default_target = "dev"

[settings]
column_contract_mode = "explicit"

[vars]
benchmark_revision = "0"

[targets.dev]
schema = "main"

[path_defaults."staging"]
materialized = "view"

[path_defaults."intermediate"]
materialized = "table"

[path_defaults."mart"]
materialized = "table"
""",
        encoding="utf-8",
    )


def _dagster_write_sources(*, project_dir: Path, source_count: int) -> None:
    sources_dir: Path = project_dir / "sources"
    sources_dir.mkdir()
    entries: str = "\n".join(
        f"""  - name: source_{index:05d}
    expression: "(SELECT {index} AS id, CAST({index} AS DOUBLE) AS amount, 'source' AS status)"
    columns:
      - name: id
        type: INTEGER
      - name: amount
        type: DOUBLE
      - name: status
        type: VARCHAR"""
        for index in range(source_count)
    )
    (sources_dir / "generated.yml").write_text(f"sources:\n{entries}\n", encoding="utf-8")


def _dagster_write_seeds(*, project_dir: Path, seed_count: int) -> None:
    seeds_dir: Path = project_dir / "seeds"
    seeds_dir.mkdir()
    schema_entries: str = "\n".join(
        f"""  - name: seed_{index:05d}
    columns:
      - name: id
        type: INTEGER
      - name: label
        type: VARCHAR"""
        for index in range(seed_count)
    )
    (seeds_dir / "generated.yml").write_text(f"seeds:\n{schema_entries}\n", encoding="utf-8")
    for index in range(seed_count):
        (seeds_dir / f"seed_{index:05d}.csv").write_text(
            f"id,label\n{index},seed_{index:05d}\n",
            encoding="utf-8",
        )


def _dagster_write_functions(*, project_dir: Path, function_count: int) -> None:
    functions_dir: Path = project_dir / "functions" / "sql"
    functions_dir.mkdir(parents=True)
    for index in range(function_count):
        (functions_dir / f"fn_{index:05d}.sql").write_text(
            """FUNCTION (
  arguments (input_value DOUBLE),
  returns DOUBLE,
);

input_value + 1
""",
            encoding="utf-8",
        )


def _dagster_write_macros(*, project_dir: Path, macro_count: int) -> None:
    macros_dir: Path = project_dir / "models" / "macros"
    macros_dir.mkdir(parents=True)
    for index in range(macro_count):
        composed_dependency: str = {
            True: (
                '\n\ndef base_offset(expression: str) -> str:\n    return f"({expression} + 1)"\n'
            ),
            False: "",
        }[index == 0]
        macro_body: str = {
            True: "    return base_offset(_offset(expression))",
            False: "    return _offset(expression)",
        }[index == 0]
        (macros_dir / f"macro_{index:05d}.py").write_text(
            f"""def _offset(expression: str) -> str:
    return f"({{expression}} + {index})"
{composed_dependency}


def macro_{index:05d}(expression: str) -> str:
{macro_body}
""",
            encoding="utf-8",
        )


def _dagster_write_schemas(*, project_dir: Path) -> None:
    schemas_dir: Path = project_dir / "schemas"
    schemas_dir.mkdir()
    (schemas_dir / "benchmark_row.sql").write_text(
        """SCHEMA (
  name benchmark_row,
  columns (
    id (type INTEGER, nullable false),
    amount (type DOUBLE),
    status (type VARCHAR),
  ),
);
""",
        encoding="utf-8",
    )


def _dagster_write_hooks(*, project_dir: Path) -> None:
    hooks_dir: Path = project_dir / "hooks" / "sql"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "before_build.sql").write_text(
        'HOOK (description "Generated pre-build hook");\n\nSELECT 1\n',
        encoding="utf-8",
    )
    (hooks_dir / "after_build.sql").write_text(
        'HOOK (description "Generated post-build hook");\n\nSELECT 2\n',
        encoding="utf-8",
    )


def _dagster_write_models(
    *,
    project_dir: Path,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
) -> None:
    for index in range(model_count):
        folder: str = _dagster_model_folder(index=index)
        model_dir: Path = project_dir / "models" / folder
        model_dir.mkdir(parents=True, exist_ok=True)
        sql: str = _dagster_model_sql(
            index=index,
            model_count=model_count,
            source_count=source_count,
            seed_count=seed_count,
            function_count=function_count,
            macro_count=macro_count,
        )
        (model_dir / f"model_{index:05d}.sql").write_text(sql, encoding="utf-8")


def _dagster_model_folder(*, index: int) -> str:
    layer_index: int = index % 10
    return {
        (True, True): "staging",
        (False, True): "intermediate",
        (False, False): "mart",
    }[(layer_index < 4, layer_index < 8)]


def _dagster_is_base_model(*, index: int) -> bool:
    return index == 0 or (index >= _SPINE_DEPTH and (index - _SPINE_DEPTH) % _TEST_CHAIN_DEPTH == 0)


def _dagster_model_header(*, index: int) -> str:
    contract_header: str = """MODEL (
  model_schema benchmark_row,
  contract enforced,
  columns (
    id (audits [not_null]),
  ),
);"""
    audit_header: str = """MODEL (
  columns (
    id (nullable false, audits [not_null]),
  ),
);"""
    return {
        (True, False): contract_header,
        (False, True): "MODEL ();",
        (False, False): audit_header,
    }[(index == 0, index >= _ATTACHED_AUDIT_COUNT)]


def _dagster_model_sql(
    *,
    index: int,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
) -> str:
    builders: dict[bool, Callable[[], str]] = {
        True: lambda: _dagster_base_model_sql(
            index=index,
            model_count=model_count,
            source_count=source_count,
        ),
        False: lambda: _dagster_dependent_model_sql(
            index=index,
            model_count=model_count,
            seed_count=seed_count,
            function_count=function_count,
            macro_count=macro_count,
        ),
    }
    return builders[_dagster_is_base_model(index=index)]()


def _dagster_base_model_sql(*, index: int, model_count: int, source_count: int) -> str:
    source_index: int = _dagster_base_source_index(index=index, source_count=source_count)
    contract_query_sql: str = f"""{_dagster_model_header(index=index)}

SELECT
  CAST(id AS INTEGER) AS id,
  CAST(amount + CAST(@@benchmark_revision AS INTEGER) AS DOUBLE) AS amount,
  CAST(status AS VARCHAR) AS status
FROM __source("source_{source_index:05d}")
"""
    regular_query_sql: str = f"""{_dagster_model_header(index=index)}

SELECT
  id,
  amount + {_dagster_generated_mapping_expression()}
    + CAST(@@benchmark_revision AS INTEGER) AS amount,
  status
FROM __source("source_{source_index:05d}")
"""
    query_sql: str = {True: contract_query_sql, False: regular_query_sql}[index == 0]
    return _dagster_pad_model_sql(
        sql=query_sql,
        target_bytes=_dagster_model_sql_size_target(index=index, model_count=model_count),
        index=index,
    )


def _dagster_dependent_model_sql(
    *,
    index: int,
    model_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
) -> str:
    previous_name: str = f"model_{index - 1:05d}"
    macro_index: int = (index // _MACRO_INTERVAL) % macro_count
    id_expression: str = {
        True: f'@macro_{macro_index:05d}("id")',
        False: f"id + {index % 7}",
    }[index % _MACRO_INTERVAL == 0]
    generated_amount_expression: str = (
        f"amount + {index % 11} + {_dagster_generated_mapping_expression()} "
        "+ CAST(@@benchmark_revision AS INTEGER)"
    )
    function_index: int = index % function_count
    amount_expression: str = {
        True: f'__udf("fn_{function_index:05d}")(amount)',
        False: generated_amount_expression,
    }[index % _FUNCTION_INTERVAL == 0]
    seed_index: int = index % seed_count
    join_sql: str = {
        True: f'\nLEFT JOIN __seed("seed_{seed_index:05d}") AS seed ON seed.id = previous.id',
        False: "",
    }[index >= _SEED_REFERENCE_START_INDEX and index % _SEED_INTERVAL == 0]
    query: str = f'''SELECT
  {id_expression} AS id,
  {amount_expression} AS amount,
  CASE WHEN id % 2 = 0 THEN 'even' ELSE 'odd' END AS status
FROM __ref("{previous_name}") AS previous{join_sql}
'''
    direct_sql: str = f"{_dagster_model_header(index=index)}\n\n{query}"
    with_sql: str = f"""{_dagster_model_header(index=index)}

WITH transformed AS (
{query.rstrip()}
)
SELECT id, amount, status FROM transformed
"""
    nested_sql: str = f"""{_dagster_model_header(index=index)}

SELECT id, amount, status
FROM (
{query.rstrip()}
) AS nested_query
"""
    model_sql: str = {
        (True, True): with_sql,
        (True, False): with_sql,
        (False, True): nested_sql,
        (False, False): direct_sql,
    }[
        (
            index % _TOP_LEVEL_WITH_INTERVAL == 0,
            index % _NESTED_QUERY_INTERVAL == 0,
        )
    ]
    return _dagster_pad_model_sql(
        sql=model_sql,
        target_bytes=_dagster_model_sql_size_target(index=index, model_count=model_count),
        index=index,
    )


def _dagster_write_tests(
    *, project_dir: Path, model_count: int, test_count: int, source_count: int
) -> None:
    tests_dir: Path = project_dir / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    tests_per_file: int = 4
    cases_per_target: int = 5
    repeated_target_count: int = (test_count + cases_per_target - 1) // cases_per_target
    for file_index in range((test_count + tests_per_file - 1) // tests_per_file):
        first_test_index: int = file_index * tests_per_file
        blocks: str = "\n".join(
            _dagster_test_block(
                test_index=test_index,
                model_count=model_count,
                source_count=source_count,
                repeated_target_count=repeated_target_count,
            )
            for test_index in range(
                first_test_index,
                min(test_count, first_test_index + tests_per_file),
            )
        )
        (tests_dir / f"test_group_{file_index:05d}.sql").write_text(blocks, encoding="utf-8")


def _dagster_test_block(
    *,
    test_index: int,
    model_count: int,
    source_count: int,
    repeated_target_count: int,
) -> str:
    group_count: int = (model_count - _SPINE_DEPTH) // _TEST_CHAIN_DEPTH
    representative_group_count: int = (group_count * 2) // 3
    group_index: int = ((test_index // 5) * representative_group_count) // repeated_target_count
    base_index: int = _SPINE_DEPTH + group_index * _TEST_CHAIN_DEPTH
    target_index: int = base_index + _TEST_CHAIN_DEPTH - 1
    source_index: int = _dagster_base_source_index(index=base_index, source_count=source_count)
    fixture_row_count: int = 40 + (test_index % 5) * 40
    return _dagster_test_sql(
        test_index=test_index,
        source_index=source_index,
        target_index=target_index,
        fixture_row_count=fixture_row_count,
        include_assertion=test_index % 7 == 0,
    )


def _dagster_test_sql(
    *,
    test_index: int,
    source_index: int,
    target_index: int,
    fixture_row_count: int,
    include_assertion: bool,
) -> str:
    fixture_rows: str = " UNION ALL\n".join(
        f"  SELECT {row} AS id, CAST({row} AS DOUBLE) AS amount, 'source' AS status"
        for row in range(fixture_row_count)
    )
    assertion_sql: str = f""",
__assert__non_negative_{target_index:05d} AS (
  SELECT * FROM __ref("model_{target_index:05d}") WHERE amount < 0
)"""
    assertion: str = {True: assertion_sql, False: ""}[include_assertion]
    return f"""TEST (name "dagster_shaped_case_{test_index:05d}");

WITH
__source__source_{source_index:05d} AS (
{fixture_rows}
),
__expected__model_{target_index:05d} AS (
  SELECT 1 AS id, CAST(1 AS DOUBLE) AS amount, 'odd' AS status
){assertion}
SELECT 1
"""


def _dagster_base_source_index(*, index: int, source_count: int) -> int:
    base_ordinal: int = {
        True: 0,
        False: 1 + (index - _SPINE_DEPTH) // _TEST_CHAIN_DEPTH,
    }[index == 0]
    return base_ordinal % source_count


def _dagster_model_sql_size_target(*, index: int, model_count: int) -> int:
    quantile: float = (index + 1) / model_count
    upper_quantiles: tuple[float, ...] = tuple(item[0] for item in _SQL_SIZE_PROFILE)
    upper_index: int = bisect_left(upper_quantiles, quantile)
    lower_quantile, lower_size = _SQL_SIZE_PROFILE[upper_index - 1]
    upper_quantile, upper_size = _SQL_SIZE_PROFILE[upper_index]
    position: float = (quantile - lower_quantile) / (upper_quantile - lower_quantile)
    return round(lower_size + position * (upper_size - lower_size))


def _dagster_generated_mapping_expression() -> str:
    clauses: str = "".join(f"WHEN id = {value:05d} THEN {value % 13:02d} " for value in range(45))
    return f"CASE {clauses} ELSE 0 END"


def _dagster_pad_model_sql(*, sql: str, target_bytes: int, index: int) -> str:
    missing_bytes: int = max(0, target_bytes - len(sql.encode()))
    line_template: str = "-- generated field 00000 maps source_metric to output_metric_00000\n"
    line_count: int = (missing_bytes + len(line_template) - 1) // len(line_template)
    comments: str = "".join(
        f"-- generated field {line:05d} maps source_metric to output_metric_{index:05d}\n"
        for line in range(line_count)
    )
    return f"{sql.rstrip()}\n{comments}"
