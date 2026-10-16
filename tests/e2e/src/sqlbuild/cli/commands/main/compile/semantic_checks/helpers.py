from __future__ import annotations

import json
import subprocess
from itertools import chain
from pathlib import Path
from typing import Any, NamedTuple, cast

from sqlbuild._native import COMPILE_REUSE_DISABLE_ENV_VAR as REUSE_DISABLE_ENV_VAR
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import run_installed_sqb


class SemanticRun(NamedTuple):
    """One compile report and exit code."""

    report: dict[str, object]
    returncode: int


def semantic_run(*, project_dir: Path, files: dict[str, str]) -> SemanticRun:
    """Write the project and compile it once."""

    for relative_path, contents in files.items():
        path: Path = project_dir / "project" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    compiled: subprocess.CompletedProcess[str] = run_installed_sqb(
        project_dir=project_dir / "project",
        args=("compile", "--json", "--no-cache"),
        env={REUSE_DISABLE_ENV_VAR: "1"},
    )
    report: dict[str, object] = json.loads(compiled.stdout.replace(str(project_dir), "<project>"))
    _ = report.pop("compile_timings", None)
    return SemanticRun(report=report, returncode=compiled.returncode)


def diagnostic_codes(report: dict[str, object]) -> tuple[str, ...]:
    """Each reported diagnostic's code, in order."""

    diagnostics: list[dict[str, Any]] = cast(list[dict[str, Any]], report["diagnostics"])
    return tuple(str(item["code"]) for item in diagnostics)


def diagnostic_notes(report: dict[str, object]) -> frozenset[str]:
    """Every note line across the reported diagnostics."""

    diagnostics: list[dict[str, Any]] = cast(list[dict[str, Any]], report["diagnostics"])
    return frozenset(chain.from_iterable(item.get("notes", ()) for item in diagnostics))
