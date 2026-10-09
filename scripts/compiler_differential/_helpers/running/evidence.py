"""Keep a differing project's engine runs where CI can upload them."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from scripts.compiler_differential.models import EngineRun

_TARGET_DIRECTORY: str = "target"
_COMPILED_TESTS: tuple[str, ...] = ("target", "compiled", "tests")
_STAT_FILE: str = "compiled-tests-stat.tsv"


def keep_failure_evidence(
    *,
    case_dir: Path,
    project_subdirectory: str | None,
    runs: tuple[EngineRun, ...],
    evidence_dir: Path,
) -> Path:
    """Copy each engine's `target/`, every command's stderr and a compiled-test stat listing."""

    destination: Path = evidence_dir / case_dir.name
    shutil.rmtree(destination, ignore_errors=True)
    for run in runs:
        project_dir: Path = case_dir / run.engine / (project_subdirectory or "")
        engine_dir: Path = destination / run.engine
        engine_dir.mkdir(parents=True)
        target: Path = project_dir / _TARGET_DIRECTORY
        if target.is_dir():
            _ = shutil.copytree(target, engine_dir / _TARGET_DIRECTORY, symlinks=True)
        for index, outcome in enumerate(run.outcomes):
            _ = (engine_dir / f"{index}-{outcome.label}.stderr").write_text(
                outcome.stderr, encoding="utf-8", errors="surrogateescape"
            )
        _ = (engine_dir / _STAT_FILE).write_text(
            _stat_listing(project_dir.joinpath(*_COMPILED_TESTS)), encoding="utf-8"
        )
    return destination


def _stat_listing(root: Path) -> str:
    """`relative path, size, mtime_ns, ctime_ns` for every file below `root`, sorted."""

    rows: list[str] = ["path\tsize\tmtime_ns\tctime_ns"]
    for directory, _, filenames in sorted(os.walk(root)):
        for filename in sorted(filenames):
            path: Path = Path(directory, filename)
            status: os.stat_result = path.stat()
            rows.append(
                f"{path.relative_to(root).as_posix()}\t{status.st_size}\t"
                f"{status.st_mtime_ns}\t{status.st_ctime_ns}"
            )
    return "\n".join(rows) + "\n"
