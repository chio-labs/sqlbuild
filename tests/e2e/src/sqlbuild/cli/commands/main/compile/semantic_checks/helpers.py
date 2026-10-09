from __future__ import annotations

import json
import subprocess
from collections import Counter
from itertools import chain
from pathlib import Path
from typing import Any, NamedTuple, cast

from sqlbuild.cli.compile_reuse.constants import REUSE_DISABLE_ENV_VAR
from sqlbuild.compiler.semantic_checks.constants import (
    COMPLETION_DEFERRAL_SITE,
    METADATA_DEFERRAL_SITE,
    TYPE_RECOVERY_DEFERRAL_SITE,
)
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import run_installed_sqb

SEMANTIC_WHEEL_SITES: tuple[str, ...] = (
    "compiler/compile/_helpers/diagnostics/type_recovery.py:_projection_spans",
    "compiler/compile/_helpers/diagnostics/details.py:_parsed_model",
    "compiler/compile/_helpers/assembly/metadata_validation.py:_function_errors",
)
SEMANTIC_DEFERRAL_SITES: frozenset[str] = frozenset(
    {COMPLETION_DEFERRAL_SITE, METADATA_DEFERRAL_SITE, TYPE_RECOVERY_DEFERRAL_SITE}
)


class EngineSemanticRun(NamedTuple):
    """One engine's compile report, semantic wheel calls and semantic-stage deferrals."""

    report: dict[str, object]
    returncode: int
    semantic_wheel_calls: int
    deferrals: tuple[tuple[str, str], ...]


def engine_semantic_run(
    *, project_dir: Path, files: dict[str, str], engine: str
) -> EngineSemanticRun:
    """Write the project and compile it once under `engine` with analysis records on."""

    for relative_path, contents in files.items():
        path: Path = project_dir / "project" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    record_dir: Path = project_dir / "records"
    compiled: subprocess.CompletedProcess[str] = run_installed_sqb(
        project_dir=project_dir / "project",
        args=("--compiler-engine", engine, "compile", "--json", "--no-cache"),
        env={REUSE_DISABLE_ENV_VAR: "1", ANALYSIS_RECORD_DIR_ENV_VAR: str(record_dir)},
    )
    report: dict[str, object] = json.loads(compiled.stdout.replace(str(project_dir), "<project>"))
    _ = report.pop("compiler_engine", None)
    _ = report.pop("compile_timings", None)
    calls: Counter[str] = Counter()
    for path in record_dir.glob("polyglot-sites-*.json"):
        for site, _, count in json.loads(path.read_text("utf-8"))["calls"]:
            calls[site] += count
    deferrals: list[tuple[str, str]] = []
    for path in sorted(record_dir.glob("analysis-deferrals-*.jsonl")):
        for line in path.read_text("utf-8").splitlines():
            record: dict[str, str] = json.loads(line)
            deferrals.append((record["kind"], record["site"]))
    return EngineSemanticRun(
        report=report,
        returncode=compiled.returncode,
        semantic_wheel_calls=sum(calls[site] for site in SEMANTIC_WHEEL_SITES),
        deferrals=tuple(filter(lambda deferral: deferral[1] in SEMANTIC_DEFERRAL_SITES, deferrals)),
    )


def diagnostic_codes(report: dict[str, object]) -> tuple[str, ...]:
    """Each reported diagnostic's code, in order."""

    diagnostics: list[dict[str, Any]] = cast(list[dict[str, Any]], report["diagnostics"])
    return tuple(str(item["code"]) for item in diagnostics)


def diagnostic_notes(report: dict[str, object]) -> frozenset[str]:
    """Every note line across the reported diagnostics."""

    diagnostics: list[dict[str, Any]] = cast(list[dict[str, Any]], report["diagnostics"])
    return frozenset(chain.from_iterable(item.get("notes", ()) for item in diagnostics))
