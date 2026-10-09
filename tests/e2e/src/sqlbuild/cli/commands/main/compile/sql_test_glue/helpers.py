from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

from sqlbuild.cli.compile_reuse.constants import REUSE_DISABLE_ENV_VAR
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import run_installed_sqb

_DURATION: re.Pattern[str] = re.compile(r"\(\d+(?:\.\d+)?m?s\)|\d+\.\d+s")
_VOLATILE_REPORT_KEYS: tuple[str, ...] = ("compiler_engine", "compile_timings")
_VOLATILE_RESULT_KEYS: frozenset[str] = frozenset({"duration_ms"})


class EngineSqlTestRun(NamedTuple):
    """One engine's compile report and test SQL, test plan inspection and test results."""

    compile_returncode: int
    compile_report: str
    compiled_tests: dict[str, str]
    inspect_returncode: int
    inspect_output: str
    test_returncode: int
    test_results: str


def engine_sql_test_run(*, root: Path, files: dict[str, str], engine: str) -> EngineSqlTestRun:
    """Write the project, then compile, inspect and run its SQL tests under one engine."""

    project_dir: Path = root / engine
    for relative_path, contents in files.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    environment: dict[str, str] = {REUSE_DISABLE_ENV_VAR: "1"}
    engine_args: tuple[str, ...] = ("--compiler-engine", engine)
    compiled: subprocess.CompletedProcess[str] = run_installed_sqb(
        project_dir=project_dir,
        args=(*engine_args, "compile", "--json", "--no-cache"),
        env=environment,
    )
    report: dict[str, object] = json.loads(compiled.stdout.replace(str(project_dir), "<project>"))
    for key in _VOLATILE_REPORT_KEYS:
        _ = report.pop(key, None)
    tests_dir: Path = project_dir / "target" / "compiled" / "tests"
    inspected: subprocess.CompletedProcess[str] = run_installed_sqb(
        project_dir=project_dir, args=(*engine_args, "test", "--inspect"), env=environment
    )
    tested: subprocess.CompletedProcess[str] = run_installed_sqb(
        project_dir=project_dir, args=(*engine_args, "test", "--json"), env=environment
    )
    return EngineSqlTestRun(
        compile_returncode=compiled.returncode,
        compile_report=json.dumps(report, indent=2),
        compiled_tests={
            path.relative_to(tests_dir).as_posix(): path.read_text("utf-8")
            for path in sorted(tests_dir.rglob("*.sql"))
        },
        inspect_returncode=inspected.returncode,
        inspect_output=_DURATION.sub("", inspected.stdout + inspected.stderr),
        test_returncode=tested.returncode,
        test_results=_stable_results(tested.stdout.replace(str(project_dir), "<project>")),
    )


def _stable_results(stdout: str) -> str:
    try:
        payload: object = json.loads(stdout, object_hook=_without_durations)
    except json.JSONDecodeError:
        return _DURATION.sub("", stdout)
    return json.dumps(payload, indent=2, sort_keys=True)


def _without_durations(value: dict[str, object]) -> dict[str, object]:
    return {key: value[key] for key in value.keys() - _VOLATILE_RESULT_KEYS}
