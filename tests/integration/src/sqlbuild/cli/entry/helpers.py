import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import sqlbuild
from sqlbuild.cli.compile_reuse.constants import REUSE_DISABLE_ENV_VAR

type LauncherRun = tuple[int, bytes, bytes]

_ELAPSED_SECONDS: re.Pattern[bytes] = re.compile(rb"\(\d+\.\d s\)")
_PHASE_SECONDS: re.Pattern[bytes] = re.compile(rb"\(\d+\.\d+s\)")
NATIVE_SQB: Path = Path(sys.executable).with_name("sqb")
PYTHON_CLI: Path = Path(sys.executable).with_name("sqlbuild-python")
PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders_shop"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n\n'
        "[connections.local]\n"
        'database = "warehouse.duckdb"\n\n'
        "[targets.dev]\n"
        'connection = "local"\n'
        'schema = "dev"\n'
    ),
    "models/orders.sql": (
        'MODEL (\n  description "One row per order",\n  materialized table,\n);\n\n'
        "SELECT 1 AS order_id, CAST('2026-04-01' AS DATE) AS ordered_on\n"
    ),
}


def write_project(project_dir: Path) -> Path:
    """Write a one-model DuckDB project."""

    for relative, contents in PROJECT_FILES.items():
        path: Path = project_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    return project_dir


def run(program: Path, *, args: tuple[str, ...], cwd: Path) -> LauncherRun:
    """Run one CLI process with reuse enabled; return its exit code, stdout and timeless stderr."""

    completed: subprocess.CompletedProcess[bytes] = subprocess.run(
        [str(program), *args],
        cwd=cwd,
        capture_output=True,
        check=False,
        env={**os.environ, "NO_COLOR": "1", REUSE_DISABLE_ENV_VAR: "0"},
        timeout=600,
    )
    return (
        completed.returncode,
        completed.stdout,
        _PHASE_SECONDS.sub(b"(s)", completed.stderr),
    )


def launch_records(project_dir: Path) -> dict[Path, int]:
    """Every launch record in the project and its modification time."""

    directory: Path = project_dir / "target" / "cache" / "launcher-v1"
    return {path: path.stat().st_mtime_ns for path in directory.glob("*.json")}


def compute_log_captures(project_dir: Path) -> set[Path]:
    """Every completed compute log capture directory."""

    return {marker.parent for marker in (project_dir / "logs").glob("*/*/complete")}


def capture_metadata(capture: Path) -> dict[str, object]:
    """A capture's final metadata."""

    return json.loads((capture / "metadata.json").read_text(encoding="utf-8"))


def without_seconds(stream: bytes) -> bytes:
    """The stream with the reuse notice's elapsed seconds blanked."""

    return _ELAPSED_SECONDS.sub(b"(s)", stream)


def compile_timings(stdout: bytes) -> dict[str, int]:
    """The `compile_timings` of a JSON compile report."""

    return json.loads(stdout)["compile_timings"]


def without_compile_timings(stdout: bytes) -> dict[str, object]:
    """Compare full reports while allowing invocation timings to differ."""

    payload: dict[str, object] = json.loads(stdout)
    _ = payload.pop("compile_timings")
    return payload


def counting_install(directory: Path, marker: Path) -> Path:
    """Install `sqb` beside a `sqlbuild-python` that logs each start to `marker`; return `sqb`."""

    directory.mkdir(parents=True)
    program: Path = Path(shutil.copy2(NATIVE_SQB, directory / NATIVE_SQB.name))
    script: Path = directory / PYTHON_CLI.name
    _ = script.write_text(
        f'#!/bin/sh\necho started >> "{marker}"\nexec "{PYTHON_CLI}" "$@"\n', encoding="utf-8"
    )
    script.chmod(0o755)
    return program


def python_starts(marker: Path) -> int:
    """How many times the logging `sqlbuild-python` started."""

    return len(marker.read_text(encoding="utf-8").splitlines())


def write_linked_project(project_dir: Path) -> Path:
    """Put the model behind a file link to an external input."""

    project: Path = write_project(project_dir)
    model: Path = project / "models" / "orders.sql"
    target: Path = project.parent / "linked_orders.sql"
    _ = model.replace(target)
    model.symlink_to(target)
    return project


def rewrite_model_preserving_mtime(project_dir: Path) -> None:
    """Change equal-length SQL bytes, including through a link, without changing mtime."""

    model: Path = project_dir / "models" / "orders.sql"
    original: os.stat_result = model.stat()
    _ = model.write_text(model.read_text().replace("1 AS order_id", "2 AS order_id"))
    os.utime(model, ns=(original.st_atime_ns, original.st_mtime_ns))


def run_with_full_output(program: Path, *, args: tuple[str, ...], cwd: Path) -> LauncherRun:
    """Run with a writable descriptor that rejects every output byte."""

    with Path("/dev/full").open("wb") as output:
        completed: subprocess.CompletedProcess[bytes] = subprocess.run(
            [str(program), *args],
            cwd=cwd,
            stdout=output,
            stderr=subprocess.PIPE,
            env={**os.environ, "NO_COLOR": "1", REUSE_DISABLE_ENV_VAR: "0"},
            check=False,
            timeout=600,
        )
    return completed.returncode, b"", completed.stderr


def startup_install(directory: Path) -> tuple[Path, Path, Path]:
    """Install a launcher in an isolated interpreter with an editable startup search path."""

    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", "--system-site-packages", str(directory)],
        check=True,
        capture_output=True,
    )
    scripts: Path = directory / "bin"
    program: Path = Path(shutil.copy2(NATIVE_SQB, scripts / "sqb"))
    handoff: Path = scripts / "sqlbuild-python"
    _ = handoff.write_text(
        f"#!{scripts / 'python'}\n"
        "from sqlbuild.cli.entry.main.launched import main\nraise SystemExit(main())\n",
        encoding="utf-8",
    )
    handoff.chmod(0o755)
    site_packages: Path = next((directory / "lib").glob("python*/site-packages"))
    _ = (site_packages / "test_dependencies.pth").write_text(
        str(Path(sqlbuild.__file__).resolve().parent.parent)
        + "\n"
        + "\n".join(str(Path(entry).resolve()) for entry in sys.path)
        + "\n",
        encoding="utf-8",
    )
    old: Path = directory.parent / "old_helpers"
    new: Path = directory.parent / "new_helpers"
    old.mkdir()
    new.mkdir()
    _ = (old / "catalog_helper.py").write_text("SQL = '1'\n", encoding="utf-8")
    _ = (new / "catalog_helper.py").write_text("SQL = '2'\n", encoding="utf-8")
    startup: Path = site_packages / "catalog.pth"
    _ = startup.write_text(str(old) + "\n", encoding="utf-8")
    return program, startup, new
