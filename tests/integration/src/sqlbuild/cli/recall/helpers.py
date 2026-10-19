"""Synthetic DuckDB projects and process helpers for local Recall tests."""

import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

PYTHON_CLI: Path = Path(sys.executable).with_name("sqlbuild-python")
EMITTED_STDOUT: bytes = b"binary \x00\xff\xfe chunk\n"
EMITTED_STDERR: bytes = "warning \u2713 from the task\n".encode()
EMITTED_TAIL: bytes = b"after the warning\n"
EMPTY_RESULT: bytes = b'{"rows": []}'
PROJECT_TOML: str = (
    'name = "orders_shop"\n'
    'adapter = "duckdb"\n'
    'default_target = "dev"\n\n'
    "[connections.local]\n"
    'database = "warehouse.duckdb"\n\n'
    "[targets.dev]\n"
    'connection = "local"\n'
    'schema = "dev"\n'
)
ORDERS_MODEL: str = (
    'MODEL (\n  description "One row per order",\n  materialized table,\n);\n\n'
    "SELECT 1 AS order_id, CAST('2026-04-01' AS DATE) AS ordered_on\n"
)
EMIT_TASK: str = (
    '"""A task that writes exact bytes to both streams."""\n\n'
    "import os\n"
    "import sys\n"
    "import time\n\n"
    "from sqlbuild.tasks import task\n\n\n"
    "@task()\n"
    "def emit_bytes(ctx):\n"
    '    """Write binary stdout, UTF-8 stderr, then more stdout."""\n\n'
    "    sys.stdout.flush()\n"
    f"    sys.stdout.buffer.write({EMITTED_STDOUT!r})\n"
    "    sys.stdout.buffer.flush()\n"
    f"    sys.stderr.write({EMITTED_STDERR.decode()!r})\n"
    "    sys.stderr.flush()\n"
    f"    sys.stdout.write({EMITTED_TAIL.decode()!r})\n"
    "    sys.stdout.flush()\n"
    '    time.sleep(float(os.environ.get("ORDERS_TASK_SLEEP_SECONDS", "0")))\n'
    "    return ctx.result()\n"
)


def write_project(project_dir: Path, *, extra_toml: str = "", targets: int = 1) -> Path:
    """Write a DuckDB project with one model and one byte-emitting task."""

    toml: str = PROJECT_TOML + extra_toml
    for index in range(1, targets):
        toml += (
            f"\n[connections.local_{index}]\n"
            f'database = "warehouse_{index}.duckdb"\n\n'
            f"[targets.dev_{index}]\n"
            f'connection = "local_{index}"\n'
            'schema = "dev"\n'
        )
    files: dict[str, str] = {
        "sqlbuild_project.toml": toml,
        "models/orders.sql": ORDERS_MODEL,
        "python/tasks/emit.py": EMIT_TASK,
    }
    for relative, contents in files.items():
        path: Path = project_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    return project_dir


def environment(**overrides: str) -> dict[str, str]:
    """The process environment for one CLI run."""

    return {**os.environ, "NO_COLOR": "1", **overrides}


def run(project_dir: Path, *args: str, **env: str) -> subprocess.CompletedProcess[bytes]:
    """Run the Python CLI once in the project and capture exact streams."""

    return subprocess.run(
        [str(PYTHON_CLI), *args],
        cwd=project_dir,
        capture_output=True,
        check=False,
        env=environment(**env),
        timeout=600,
    )


def start(project_dir: Path, *args: str, **env: str) -> subprocess.Popen[bytes]:
    """Start the Python CLI in its own process group."""

    return subprocess.Popen(
        [str(PYTHON_CLI), *args],
        cwd=project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment(**env),
        start_new_session=True,
    )


def recall_rows(project_dir: Path, sql: str) -> list[list[object]]:
    """The rows `sqb recall query --json` returns."""

    completed: subprocess.CompletedProcess[bytes] = run(
        project_dir, "recall", "query", "--json", "--no-limit", sql
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    return json.loads(completed.stdout)["rows"]


def wait_for(predicate_sql: str, project_dir: Path, *, timeout: float) -> list[list[object]]:
    """Poll the store until `predicate_sql` returns a row; a store not yet created has none."""

    deadline: float = time.monotonic() + timeout
    rows: list[list[object]] = []
    while time.monotonic() < deadline and not rows:
        time.sleep(0.2)
        completed: subprocess.CompletedProcess[bytes] = run(
            project_dir, "recall", "query", "--json", predicate_sql
        )
        rows = json.loads(completed.stdout or EMPTY_RESULT)["rows"]
    return rows


def build_with_read_only_logs(
    project_dir: Path,
) -> tuple[subprocess.CompletedProcess[bytes], subprocess.CompletedProcess[bytes]]:
    """Two builds while the project's `logs` directory cannot be written."""

    logs: Path = project_dir / "logs"
    logs.mkdir()
    logs.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        return run(project_dir, "build"), run(project_dir, "build")
    finally:
        logs.chmod(stat.S_IRWXU)


def killed_build(project_dir: Path, *, heartbeat_seconds: str) -> tuple[str, list[list[object]]]:
    """The running invocation a SIGKILLed build left, and the store's rows for it afterwards."""

    process: subprocess.Popen[bytes] = start(
        project_dir,
        "build",
        SQLBUILD_RECALL_HEARTBEAT_SECONDS=heartbeat_seconds,
        ORDERS_TASK_SLEEP_SECONDS="60",
    )
    running: list[list[object]] = wait_for(
        "SELECT invocation_id FROM invocations WHERE status = 'running' "
        "AND invocation_id IN (SELECT invocation_id FROM recall_output)",
        project_dir,
        timeout=120,
    )
    os.killpg(process.pid, signal.SIGKILL)
    _ = process.wait(timeout=30)
    time.sleep(5 * float(heartbeat_seconds))
    recorded: list[list[object]] = recall_rows(
        project_dir,
        "SELECT i.invocation_id, i.status, i.ended_at IS NOT NULL, o.complete "
        "FROM invocations i JOIN output_invocations o USING (invocation_id)",
    )
    return str(running[0][0]), recorded


def concurrent_builds(project_dir: Path, targets: tuple[str, ...]) -> tuple[list[int], int, int]:
    """Exit codes of concurrent builds, reads made meanwhile and unexpected read failures."""

    _ = run(project_dir, "recall", "query", "SELECT 1")
    builds: list[subprocess.Popen[bytes]] = [
        start(project_dir, "build", "--target", target) for target in targets
    ]
    reads: int = 0
    unexpected_failures: int = 0
    while any(build.poll() is None for build in builds):
        reader: subprocess.CompletedProcess[bytes] = run(
            project_dir, "recall", "query", "--json", "SELECT COUNT(*) FROM invocations"
        )
        reads += 1
        unexpected_failures += int(reader.returncode != 0 and b"[C971]" not in reader.stderr)
    return [build.wait(timeout=600) for build in builds], reads, unexpected_failures
