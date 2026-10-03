"""Generated project helpers for format performance guards."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash

_FORMAT_ELAPSED_PATTERN: re.Pattern[str] = re.compile(r"Formatting SQL  OK  \(([0-9.]+)s;")


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
            'MODEL (description "Test model.", '
            "columns (order_id (type INTEGER), note (type VARCHAR)));\n"
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


def run_format_check(
    *, project_dir: Path, timeout_seconds: float
) -> tuple[subprocess.CompletedProcess[str], float, float]:
    """Run `sqb format --check` and return the result, wall time and format-phase time."""

    started_at: float = time.perf_counter()
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--project-dir",
            str(project_dir),
            "--no-color",
            "format",
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    elapsed_seconds: float = time.perf_counter() - started_at
    elapsed_match: re.Match[str] | None = _FORMAT_ELAPSED_PATTERN.search(result.stderr)
    assert elapsed_match is not None, result.stderr
    return result, elapsed_seconds, float(elapsed_match.group(1))


def compiled_contract(*, project_dir: Path) -> dict[str, list[tuple[object, ...]]]:
    """Compile a project; return each resource's dependencies, lineage, columns and fingerprint."""

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--project-dir",
            str(project_dir),
            "compile",
            "--no-cache",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    resources: dict[str, list[dict[str, object]]] = json.loads(result.stdout)["resources"]
    contract: dict[str, list[tuple[object, ...]]] = {}
    for kind, entries in resources.items():
        rows: list[tuple[object, ...]] = [_resource_contract(entry) for entry in entries]
        contract[kind] = sorted(rows, key=repr)
    return contract


def _resource_contract(resource: dict[str, object]) -> tuple[object, ...]:
    return (
        resource.get("name"),
        json.dumps(resource.get("depends_on"), sort_keys=True),
        json.dumps(resource.get("lineage"), sort_keys=True),
        resource.get("column_count"),
        compute_query_hash(query_sql=str(resource.get("query_sql", "")), dialect="duckdb"),
    )


def run_sqb(*, project_dir: Path, arguments: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """Run one `sqb` command against a project and capture its output."""

    return subprocess.run(
        [str(Path(sys.executable).with_name("sqb")), "--project-dir", str(project_dir), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
