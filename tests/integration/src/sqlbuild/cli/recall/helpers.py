"""Synthetic DuckDB projects and process helpers for local Recall tests."""

import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

PYTHON_CLI: Path = Path(sys.executable).with_name("sqlbuild-python")
EMITTED_STDOUT: bytes = b"binary \x00\xff\xfe chunk\n"
EMITTED_STDERR: bytes = "warning \u2713 from the task\n".encode()
EMITTED_TAIL: bytes = b"after the warning\n"
EMPTY_RESULT: bytes = b'{"rows": []}'
NUMBERED_LINE: re.Pattern[bytes] = re.compile(rb"^(\d+) std(?:out|err)$", re.MULTILINE)
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
    "import itertools\n"
    "import os\n"
    "import sys\n"
    "import threading\n"
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
    '    _write_concurrently(int(os.environ.get("ORDERS_TASK_THREAD_LINES", "0")))\n'
    '    sys.stdout.write("y" * int(os.environ.get("ORDERS_TASK_STDOUT_BYTES", "0")))\n'
    "    sys.stdout.flush()\n"
    "    return ctx.result()\n\n\n"
    "def _write_concurrently(lines):\n"
    '    """Two threads write numbered lines; the number gives the true global order."""\n\n'
    "    lock = threading.Lock()\n"
    "    counter = itertools.count()\n\n"
    "    def writer(name, stream):\n"
    "        for _ in range(lines):\n"
    "            with lock:\n"
    '                stream.write(f"{next(counter)} {name}\\n")\n'
    "                stream.flush()\n\n"
    "    threads = [\n"
    '        threading.Thread(target=writer, args=("stdout", sys.stdout)),\n'
    '        threading.Thread(target=writer, args=("stderr", sys.stderr)),\n'
    "    ]\n"
    "    for thread in threads:\n"
    "        thread.start()\n"
    "    for thread in threads:\n"
    "        thread.join()\n"
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


def timed_build(project_dir: Path) -> tuple[subprocess.CompletedProcess[bytes], float, float]:
    """A build with the seconds until its first stderr byte and until it exited."""

    started: float = time.monotonic()
    process: subprocess.Popen[bytes] = start(project_dir, "build")
    assert process.stderr is not None
    first_byte: bytes = process.stderr.read(1)
    first_output: float = time.monotonic() - started
    stdout, stderr = process.communicate(timeout=600)
    return (
        subprocess.CompletedProcess(process.args, process.returncode, stdout, first_byte + stderr),
        first_output,
        time.monotonic() - started,
    )


@contextmanager
def held_store_lock(project_dir: Path) -> Iterator[None]:
    """Another process holds the store's write lock while the block runs, creating it if absent."""

    store: Path = project_dir / "logs" / "recall.sqlite3"
    store.parent.mkdir(parents=True, exist_ok=True)
    holder: subprocess.Popen[bytes] = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sqlite3, sys, time\n"
            "connection = sqlite3.connect(sys.argv[1], isolation_level=None)\n"
            "connection.execute('BEGIN EXCLUSIVE')\n"
            "print('locked', flush=True)\n"
            "time.sleep(600)\n",
            str(store),
        ],
        stdout=subprocess.PIPE,
    )
    try:
        assert holder.stdout is not None
        _ = holder.stdout.readline()
        yield
    finally:
        holder.kill()
        _ = holder.wait(timeout=30)


def build_while_store_locked(
    project_dir: Path,
) -> tuple[subprocess.CompletedProcess[bytes], float, float]:
    """A timed build while another process holds the store's write lock."""

    with held_store_lock(project_dir):
        return timed_build(project_dir)


def compute_log_streams(project_dir: Path, invocation_id: str) -> tuple[bytes, bytes]:
    """The stdout and stderr bytes compute logs captured for one invocation."""

    capture: Path = next((project_dir / "logs").glob(f"*/{invocation_id}"))
    return (capture / "stdout.log").read_bytes(), (capture / "stderr.log").read_bytes()


def write_corrupt_store(project_dir: Path) -> None:
    """Replace the Recall store with a file that is not a database."""

    store: Path = project_dir / "logs" / "recall.sqlite3"
    store.parent.mkdir(parents=True, exist_ok=True)
    _ = store.write_bytes(b"this file is not a database\n")


FAILING_RECALL_STDERR: str = (
    "import sys\n\n\n"
    "class _RejectsRecallNotices:\n"
    "    def __init__(self, stream):\n"
    "        self._stream = stream\n\n"
    "    def write(self, text):\n"
    '        if "Recall" in text:\n'
    '            raise OSError("stderr rejected the Recall notice")\n'
    "        return self._stream.write(text)\n\n"
    "    def __getattr__(self, name):\n"
    "        return getattr(self._stream, name)\n\n\n"
    "sys.stderr = _RejectsRecallNotices(sys.stderr)\n"
)


def build_with_failing_recall_notices(project_dir: Path, site_dir: Path) -> int:
    """The exit code of a build whose Recall notices fail to write, while the store is locked."""

    site_dir.mkdir(parents=True, exist_ok=True)
    _ = (site_dir / "sitecustomize.py").write_text(FAILING_RECALL_STDERR, encoding="utf-8")
    with held_store_lock(project_dir):
        return run(project_dir, "build", PYTHONPATH=str(site_dir)).returncode


def prepared_project(parent: Path, extra_toml: str, *, builds: int) -> Path:
    """A project under `parent`, built `builds` times first."""

    project_dir: Path = write_project(parent / "orders_shop", extra_toml=extra_toml)
    _ = [run(project_dir, "build") for _ in range(builds)]
    return project_dir


def numbered_lines(output: bytes) -> list[int]:
    """The leading numbers of the numbered lines in `output`, in order."""

    return [int(number) for number in NUMBERED_LINE.findall(output)]


def simultaneous_builds(project_dir: Path, targets: tuple[str, ...]) -> list[int]:
    """Exit codes of builds of `targets`, each with its own warehouse, started together."""

    started: list[subprocess.Popen[bytes]] = [
        start(project_dir, "build", "--target", target) for target in targets
    ]
    return [process.wait(timeout=600) for process in started]
