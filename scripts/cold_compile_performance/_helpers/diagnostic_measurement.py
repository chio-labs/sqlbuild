"""Fresh-process and location-only measurements for diagnostic workloads."""

import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

from scripts.cold_compile_performance.exceptions import CompileBenchmarkFixtureError
from sqlbuild.compiler.compile._helpers.assembly.binding_positions import (
    get_authored_binding_location,
)
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic
from sqlbuild.spec.contracts.models import SourceLocation


def measure_diagnostic_compile(
    *, project_dir: Path, timeout: float
) -> tuple[float, dict[str, Any]]:
    """Keep invalid-project exit codes and diagnostics part of the performance contract."""
    started: float = perf_counter()
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from sqlbuild.cli.entry.main.entry import main; sys.exit(main())",
            "--project-dir",
            str(project_dir),
            "compile",
            "--no-cache",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    elapsed: float = perf_counter() - started
    (project_dir / "measurement.json").write_text(
        json.dumps({"elapsed": elapsed, "returncode": result.returncode})
    )
    (project_dir / "compile.stderr").write_text(result.stderr)
    (project_dir / "compile.json").write_text(result.stdout)
    if result.returncode != 1:
        raise CompileBenchmarkFixtureError(
            f"expected diagnostic failure, got {result.returncode}: {result.stderr}"
        )
    return elapsed, json.loads(result.stdout)


def measure_position_mapping(*, count: int, lines: int = 4000) -> float:
    """Measure many spans against one large normalized macro-expanded SQL body."""
    original: str = (
        "SELECT\n"
        + ",\n".join(f"  amount + {index} AS amount_{index}" for index in range(lines))
        + '\nFROM __ref("orders") WHERE amount > 5'
    )
    normalized: str = original.replace('__ref("orders")', '"orders"').replace("\n", " ")
    offset: int = normalized.index("amount > 5")
    diagnostic: SqlBindingDiagnostic = SqlBindingDiagnostic(
        code="B217", message="Incompatible comparison", start=offset, end=offset + len("amount > 5")
    )
    started: float = perf_counter()
    for _ in range(count):
        location: SourceLocation | None = get_authored_binding_location(
            path=Path("models/orders.sql"),
            authored_sql=original,
            authored_query_sql=original,
            cleaned_sql=normalized,
            diagnostic=diagnostic,
        )
        if location is None or location.line != lines + 2:
            raise CompileBenchmarkFixtureError(
                "mapping must preserve the authored comparison location"
            )
    return perf_counter() - started
