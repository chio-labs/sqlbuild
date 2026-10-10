from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from itertools import product
from pathlib import Path
from typing import NamedTuple, cast

from sqlbuild.cli.compile_reuse.constants import REUSE_DISABLE_ENV_VAR
from sqlbuild.compiler.lineage.constants import NATIVE_LINEAGE_DEFERRAL_SITE
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import run_installed_sqb

_TIMING: re.Pattern[str] = re.compile(r" \(\d+\.\d+s\)")
_DIRECTIONS: tuple[str, ...] = ("upstream", "downstream")
FALLBACK_SITE: str = (
    "compiler/lineage/_helpers/fast_columns.py:_build_polyglot_fast_model_column_lineage"
)


class EngineLineageRun(NamedTuple):
    """One engine's compile report, lineage traces, wheel calls and deferrals."""

    compile_report: str
    compile_returncode: int
    traces: list[tuple[int, str, str]]
    fallback_parses: int
    lineage_deferrals: int
    wheel_calls: int


def engine_lineage_run(
    *,
    project_dir: Path,
    files: dict[str, str],
    engine: str,
    targets: tuple[str, ...],
    mode: str = "fast",
) -> EngineLineageRun:
    """Write the project, then compile and trace every target both ways in one lineage mode."""

    for relative_path, contents in files.items():
        path: Path = project_dir / "project" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    record_dir: Path = project_dir / "records"
    environment: dict[str, str] = {
        REUSE_DISABLE_ENV_VAR: "1",
        ANALYSIS_RECORD_DIR_ENV_VAR: str(record_dir),
    }
    engine_args: tuple[str, ...] = ("--compiler-engine", engine)
    compiled: subprocess.CompletedProcess[str] = run_installed_sqb(
        project_dir=project_dir / "project",
        args=(*engine_args, "compile", "--json", "--no-cache", "--lineage-mode", mode),
        env=environment,
    )
    report: dict[str, object] = json.loads(compiled.stdout.replace(str(project_dir), "<project>"))
    _ = report.pop("compiler_engine", None)
    _ = report.pop("compile_timings", None)
    traces: list[tuple[int, str, str]] = []
    for target, direction in product(targets, _DIRECTIONS):
        result: subprocess.CompletedProcess[str] = run_installed_sqb(
            project_dir=project_dir / "project",
            args=(
                *engine_args,
                "lineage",
                target,
                "--mode",
                mode,
                "--direction",
                direction,
                "--json",
            ),
            env=environment,
        )
        stdout: str = result.stdout.replace(str(project_dir), "<project>")
        traces.append((result.returncode, stdout, _TIMING.sub("", result.stderr)))
    wheel_calls: Counter[str] = _site_calls(record_dir)
    return EngineLineageRun(
        compile_report=json.dumps(report, indent=2),
        compile_returncode=compiled.returncode,
        traces=traces,
        fallback_parses=wheel_calls[FALLBACK_SITE],
        lineage_deferrals=sum(
            path.read_text("utf-8").count(f'"site": "{NATIVE_LINEAGE_DEFERRAL_SITE}"')
            for path in record_dir.glob("analysis-deferrals-*.jsonl")
        ),
        wheel_calls=wheel_calls.total(),
    )


class FailedLineageRun(NamedTuple):
    """A failed command's return code, last stderr line and polyglot wheel calls."""

    returncode: int
    last_error_line: str
    wheel_calls: int


def failed_rich_lineage_run(
    *, project_dir: Path, files: dict[str, str], args: tuple[str, ...], perturbation: str
) -> FailedLineageRun:
    """Run one command with `perturbation` installed as `sitecustomize` in the CLI process."""

    for relative_path, contents in files.items():
        path: Path = project_dir / "project" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    extlib: Path = project_dir / "extlib"
    extlib.mkdir()
    _ = (extlib / "sitecustomize.py").write_text(perturbation, encoding="utf-8")
    record_dir: Path = project_dir / "records"
    result: subprocess.CompletedProcess[str] = run_installed_sqb(
        project_dir=project_dir / "project",
        args=args,
        env={
            REUSE_DISABLE_ENV_VAR: "1",
            ANALYSIS_RECORD_DIR_ENV_VAR: str(record_dir),
            "PYTHONPATH": str(extlib),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    return FailedLineageRun(
        returncode=result.returncode,
        last_error_line=(result.stderr.strip().splitlines() or [""])[-1],
        wheel_calls=_site_calls(record_dir).total(),
    )


def model_lineage_summaries(compile_report: str) -> dict[str, object]:
    """The `lineage` summary of every model in a JSON compile report, by model name."""

    payload: dict[str, object] = json.loads(compile_report)
    models: list[dict[str, object]] = cast(
        list[dict[str, object]], cast(dict[str, object], payload["resources"])["models"]
    )
    return {str(model["name"]): model["lineage"] for model in models}


def _site_calls(record_dir: Path) -> Counter[str]:
    calls: Counter[str] = Counter()
    for path in record_dir.glob("polyglot-sites-*.json"):
        for site, _, count in json.loads(path.read_text("utf-8"))["calls"]:
            calls[site] += count
    return calls
