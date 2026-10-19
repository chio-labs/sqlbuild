import os
import re
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import sqlbuild
from sqlbuild._native import COMPILE_REUSE_DISABLE_ENV_VAR as REUSE_DISABLE_ENV_VAR
from tests.integration.src.sqlbuild.cli.entry.python_host._test_types import HostedRun

NATIVE_SQB: Path = Path(sys.executable).with_name("sqb")
HOST_MODE_VARIABLE: str = "SQLBUILD_HOST_MODE"
HOST_REPORT_VARIABLE: str = "SQLBUILD_PYTHON_HOST"
PROBE_ACTION_VARIABLE: str = "SQLBUILD_TEST_HOST_ACTION"
PROBE_EXIT_VARIABLE: str = "SQLBUILD_TEST_HOST_EXIT"
PROBE_READY_VARIABLE: str = "SQLBUILD_TEST_HOST_READY"
PROBE_STARTS_VARIABLE: str = "SQLBUILD_TEST_PYTHON_STARTS"
PLAIN_SCRIPT_HEAD: str = "#!{scripts}/python\n"
RELOCATABLE_SCRIPT_HEAD: str = (
    "#!/bin/sh\n"
    '\'\'\'exec\' "$(dirname -- "$(realpath -- "$0")")"/\'python\' "$0" "$@"\n'
    "' '''\n"
)
SCRIPT_BODY: str = (
    "import sys\n"
    "from sqlbuild.cli.entry.main.launched import main\n"
    'if __name__ == "__main__":\n'
    "    sys.exit(main())\n"
)
_PHASE_SECONDS: re.Pattern[bytes] = re.compile(rb"\(\d+\.\d+ ?s\)")
# Imported by `site` at start-up in both host modes: counts Python starts and, when asked,
# replaces the CLI with a probe that reports the interpreter, writes both streams, fails or waits.
HOST_PROBE: str = """\
import json
import os
import sys
import time

_starts = os.environ.get("SQLBUILD_TEST_PYTHON_STARTS")
if _starts:
    with open(_starts, "a", encoding="utf-8") as _log:
        _log.write("started\\n")
_action = os.environ.get("SQLBUILD_TEST_HOST_ACTION")
if _action:
    import sqlbuild.cli.entry.main.entry as _entry

    def _describe(argv):
        print(json.dumps({
            "executable": sys.executable,
            "prefix": sys.prefix,
            "base_prefix": sys.base_prefix,
            "argv0": sys.argv[0],
            "argv": [a for a in argv if not a.startswith("--sqlbuild-launch-record=")],
            "path": sys.path,
            "host": os.environ.get("SQLBUILD_PYTHON_HOST"),
        }))
        return 0

    def _streams(argv):
        for index in range(3):
            print(f"out {index}", flush=True)
            print(f"err {index}", file=sys.stderr, flush=True)
        return int(os.environ["SQLBUILD_TEST_HOST_EXIT"])

    def _fail(argv):
        raise RuntimeError("host probe failure")

    def _wait(argv):
        open(os.environ["SQLBUILD_TEST_HOST_READY"], "w").close()
        time.sleep(120)
        return 0

    _entry.main = {"describe": _describe, "streams": _streams, "fail": _fail, "wait": _wait}[
        _action
    ]
"""


def dependency_paths() -> list[str]:
    """The SQLBuild source root and this interpreter's import path, for isolated installs."""

    source_root: str = str(Path(sqlbuild.__file__).resolve().parent.parent)
    return [source_root, *(str(Path(entry).resolve()) for entry in filter(None, sys.path))]


def dependencies_in_pth(venv: Path) -> list[str]:
    """Put SQLBuild and its dependencies on the venv's path with a `.pth` file."""

    site_packages: Path = next((venv / "lib").glob("python*/site-packages"))
    _ = (site_packages / "test_dependencies.pth").write_text(
        "\n".join(dependency_paths()) + "\n", encoding="utf-8"
    )
    return []


def dependencies_on_pythonpath(venv: Path) -> list[str]:
    """Leave the venv bare; SQLBuild and its dependencies come from `PYTHONPATH`."""

    del venv
    return dependency_paths()


def host_install(
    directory: Path,
    *,
    interpreter: Path,
    script_head: str,
    install_dependencies: Callable[[Path], list[str]],
) -> tuple[Path, list[str]]:
    """Install `sqb` and a `sqlbuild-python` script in a new venv; return `sqb` and extra paths."""

    subprocess.run(
        [str(interpreter), "-m", "venv", "--without-pip", str(directory)],
        check=True,
        capture_output=True,
    )
    scripts: Path = directory / "bin"
    program: Path = Path(shutil.copy2(NATIVE_SQB, scripts / "sqb"))
    script: Path = scripts / "sqlbuild-python"
    head: str = script_head.replace("{scripts}", str(scripts))
    _ = script.write_text(head + SCRIPT_BODY, encoding="utf-8")
    script.chmod(0o755)
    extra_paths: list[str] = install_dependencies(directory)
    return program, extra_paths


def base_executable() -> Path:
    """This interpreter's base installation executable."""

    version: str = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return Path(sys.base_prefix) / "bin" / version


def base_needs_shared_libpython() -> bool:
    """Whether the base executable loads a shared libpython, so a copy of it cannot start alone."""

    ldd: str | None = shutil.which("ldd")
    linked: subprocess.CompletedProcess[str] = subprocess.run(
        [ldd or "false", str(base_executable())], capture_output=True, text=True, check=False
    )
    return linked.returncode != 0 or "libpython" in linked.stdout


def static_base(directory: Path) -> Path:
    """A copy of the base interpreter with the standard library linked in and no libpython."""

    executable: Path = base_executable()
    (directory / "bin").mkdir(parents=True)
    (directory / "lib").mkdir()
    copied: Path = Path(shutil.copy2(executable, directory / "bin" / executable.name))
    stdlib: Path = Path(sys.base_prefix) / "lib" / executable.name
    (directory / "lib" / executable.name).symlink_to(stdlib, target_is_directory=True)
    return copied


def write_host_probe(directory: Path) -> Path:
    """Write the start-up probe module into `directory` and return the directory."""

    directory.mkdir(parents=True, exist_ok=True)
    _ = (directory / "sitecustomize.py").write_text(HOST_PROBE, encoding="utf-8")
    return directory


def host_environment(
    *, mode: str, cache: Path, extra: dict[str, str] | None = None
) -> dict[str, str]:
    """This environment with `mode` as the host mode (empty: automatic) and an isolated cache."""

    environment: dict[str, str] = dict(os.environ)
    for name in (HOST_MODE_VARIABLE, HOST_REPORT_VARIABLE):
        environment.pop(name, None)
    environment.update(
        {
            "NO_COLOR": "1",
            REUSE_DISABLE_ENV_VAR: "0",
            "XDG_CACHE_HOME": str(cache),
            HOST_MODE_VARIABLE: mode,
            **(extra or {}),
        }
    )
    return environment


def timeless(stream: bytes) -> bytes:
    """The stream with phase durations blanked."""

    return _PHASE_SECONDS.sub(b"(s)", stream)


def run_hosted(
    program: Path, args: tuple[str, ...], cwd: Path, environment: dict[str, str]
) -> HostedRun:
    """Run `program`; return its exit code, stdout and stderr with durations blanked."""

    completed: subprocess.CompletedProcess[bytes] = subprocess.run(
        [str(program), *args],
        cwd=cwd,
        capture_output=True,
        env=environment,
        check=False,
        timeout=600,
    )
    return completed.returncode, timeless(completed.stdout), timeless(completed.stderr)


def run_hosted_merged(
    program: Path, args: tuple[str, ...], cwd: Path, environment: dict[str, str]
) -> HostedRun:
    """Run `program` with stderr on stdout's pipe; return the exit code and the merged output."""

    completed: subprocess.CompletedProcess[bytes] = subprocess.run(
        [str(program), *args],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=environment,
        check=False,
        timeout=600,
    )
    return completed.returncode, timeless(completed.stdout), b""


def _restore_default_interrupt() -> None:
    _ = signal.signal(signal.SIGINT, signal.SIG_DFL)


def interrupt_hosted(program: Path, *, cwd: Path, environment: dict[str, str]) -> HostedRun:
    """Start `program`, interrupt it with SIGINT once the probe is waiting, and collect it."""

    ready: Path = Path(environment[PROBE_READY_VARIABLE])
    process: subprocess.Popen[bytes] = subprocess.Popen(
        [str(program), "--help"],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        preexec_fn=_restore_default_interrupt,
    )
    deadline: float = time.monotonic() + 60.0
    while not ready.exists() and time.monotonic() < deadline and process.poll() is None:
        time.sleep(0.05)
    process.send_signal(signal.SIGINT)
    stdout, stderr = process.communicate(timeout=60)
    return process.returncode, stdout, stderr


def starts_log(path: Path) -> Path:
    """An empty log the probe appends one line to per Python start."""

    _ = path.write_text("", encoding="utf-8")
    return path


def python_starts(log: Path) -> int:
    """How many Python processes the probe saw start."""

    return len(log.read_text(encoding="utf-8").splitlines())
