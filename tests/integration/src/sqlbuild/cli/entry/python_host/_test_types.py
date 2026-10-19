from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

type HostedRun = tuple[int, bytes, bytes]
type HostedRunner = Callable[[Path, tuple[str, ...], Path, dict[str, str]], HostedRun]


@dataclass(frozen=True)
class HostLayoutTestCase:
    """One way an environment installs `sqb`, its Python CLI script and SQLBuild."""

    description: str
    script_head: str
    install_dependencies: Callable[[Path], list[str]]
    expected_embedded_report_prefix: str
    expected_exec_report: str


@dataclass(frozen=True)
class HostParityTestCase:
    """One `sqb` invocation whose outcome must not depend on how Python was started."""

    description: str
    args: tuple[str, ...]
    project_files: dict[str, str]
    working_dir: str
    runner: HostedRunner
    expected_exit_code: int


@dataclass(frozen=True)
class HostExitTestCase:
    """An exit status the Python CLI returns after writing to both streams."""

    description: str
    exit_code: int
    expected_run: HostedRun


@dataclass(frozen=True)
class HostTracebackTestCase:
    """An exception the Python CLI does not catch."""

    description: str
    expected_exit_code: int
    expected_stderr_start: bytes
    expected_stderr_end: bytes


@dataclass(frozen=True)
class HostInterruptTestCase:
    """A SIGINT sent while the Python CLI runs."""

    description: str
    expected_exit_codes: tuple[int, ...]
    expected_stderr_fragment: bytes


@dataclass(frozen=True)
class HostFallbackTestCase:
    """An interpreter without a shared libpython and what each host mode does with it."""

    description: str
    expected_report_prefix: str
    expected_report_fragment: str
    expected_cache_files: int
    expected_required_exit_code: int
    expected_required_error: bytes


@dataclass(frozen=True)
class HostReplayTestCase:
    """A repeated compile that `sqb` replays without starting Python."""

    description: str
    args: tuple[str, ...]
    expected_python_starts: tuple[int, int]
    expected_notice: bytes
