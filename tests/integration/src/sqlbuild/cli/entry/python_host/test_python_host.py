"""`sqb` runs the Python CLI in its own process exactly as running its script would."""

import json
import os
import shutil
import signal
import sys
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.entry.helpers import write_project
from tests.integration.src.sqlbuild.cli.entry.python_host._test_types import (
    HostedRun,
    HostExitTestCase,
    HostFallbackTestCase,
    HostInterruptTestCase,
    HostLayoutTestCase,
    HostParityTestCase,
    HostReplayTestCase,
    HostTracebackTestCase,
)
from tests.integration.src.sqlbuild.cli.entry.python_host.helpers import (
    NATIVE_SQB,
    PLAIN_SCRIPT_HEAD,
    PROBE_ACTION_VARIABLE,
    PROBE_EXIT_VARIABLE,
    PROBE_READY_VARIABLE,
    PROBE_STARTS_VARIABLE,
    RELOCATABLE_SCRIPT_HEAD,
    base_needs_shared_libpython,
    dependencies_in_pth,
    dependencies_on_pythonpath,
    host_environment,
    host_install,
    interrupt_hosted,
    python_starts,
    run_hosted,
    run_hosted_merged,
    starts_log,
    static_base,
    write_host_probe,
)

pytestmark: pytest.MarkDecorator = pytest.mark.skipif(
    sys.platform != "linux", reason="sqb runs Python in its own process only on Linux"
)
BROKEN_MODEL: dict[str, str] = {
    "models/broken.sql": (
        'MODEL (description "Broken", materialized table);\n\nSELEC 1 AS order_id\n'
    )
}


@pytest.mark.parametrize(
    "test_case",
    [
        HostLayoutTestCase(
            description="venv with a #! script and SQLBuild from a .pth file",
            script_head=PLAIN_SCRIPT_HEAD,
            install_dependencies=dependencies_in_pth,
            expected_embedded_report_prefix="embedded (libpython ",
            expected_exec_report="exec (SQLBUILD_HOST_MODE=exec)",
        ),
        HostLayoutTestCase(
            description="uv relocatable trampoline",
            script_head=RELOCATABLE_SCRIPT_HEAD,
            install_dependencies=dependencies_in_pth,
            expected_embedded_report_prefix="embedded (libpython ",
            expected_exec_report="exec (SQLBUILD_HOST_MODE=exec)",
        ),
        HostLayoutTestCase(
            description="SQLBuild on PYTHONPATH",
            script_head=PLAIN_SCRIPT_HEAD,
            install_dependencies=dependencies_on_pythonpath,
            expected_embedded_report_prefix="embedded (libpython ",
            expected_exec_report="exec (SQLBUILD_HOST_MODE=exec)",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_install_layout_when_hosting_then_python_matches_the_script_interpreter(
    test_case: HostLayoutTestCase, tmp_path: Path
) -> None:
    program, extra_paths = host_install(
        tmp_path / "venv",
        interpreter=Path(sys.executable),
        script_head=test_case.script_head,
        install_dependencies=test_case.install_dependencies,
    )
    probe: Path = write_host_probe(tmp_path / "probe")
    extra: dict[str, str] = {
        "PYTHONPATH": os.pathsep.join([str(probe), *extra_paths]),
        PROBE_ACTION_VARIABLE: "describe",
    }
    reports: dict[str, dict[str, object]] = {}
    for mode in ("embedded", "exec", ""):
        environment: dict[str, str] = host_environment(
            mode=mode, cache=tmp_path / "cache", extra=extra
        )
        hosted: HostedRun = run_hosted(program, ("compile", "--json"), tmp_path, environment)
        assert hosted[0] == 0, hosted[2]
        reports[mode] = json.loads(hosted[1])
    embedded, executed, automatic = reports["embedded"], reports["exec"], reports[""]

    embedded_report: str = str(embedded.pop("host"))

    assert embedded_report.startswith(test_case.expected_embedded_report_prefix)
    assert executed.pop("host") == test_case.expected_exec_report
    assert automatic.pop("host") == embedded_report
    assert embedded == executed == automatic
    assert Path(str(embedded["prefix"])).resolve() == (tmp_path / "venv").resolve()
    assert embedded["argv"] == ["compile", "--json"]


@pytest.mark.parametrize(
    "test_case",
    [
        HostParityTestCase(
            description="help",
            args=("--help",),
            project_files={},
            working_dir=".",
            runner=run_hosted,
            expected_exit_code=0,
        ),
        HostParityTestCase(
            description="unknown command",
            args=("not-a-command",),
            project_files={},
            working_dir=".",
            runner=run_hosted,
            expected_exit_code=2,
        ),
        HostParityTestCase(
            description="compile outside a project",
            args=("compile", "--json"),
            project_files={},
            working_dir=".",
            runner=run_hosted,
            expected_exit_code=1,
        ),
        HostParityTestCase(
            description="text compile",
            args=("compile",),
            project_files={},
            working_dir="project",
            runner=run_hosted,
            expected_exit_code=0,
        ),
        HostParityTestCase(
            description="failing compile with interleaved streams",
            args=("compile",),
            project_files=BROKEN_MODEL,
            working_dir="project",
            runner=run_hosted_merged,
            expected_exit_code=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cli_invocation_when_hosting_embedded_or_exec_then_output_is_identical(
    test_case: HostParityTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "project")
    for relative, contents in test_case.project_files.items():
        _ = (project_dir / relative).write_text(contents, encoding="utf-8")
    runs: dict[str, HostedRun] = {}
    for mode in ("embedded", "exec"):
        shutil.rmtree(project_dir / "target", ignore_errors=True)
        environment: dict[str, str] = host_environment(mode=mode, cache=tmp_path / "cache")
        runs[mode] = test_case.runner(
            NATIVE_SQB, test_case.args, tmp_path / test_case.working_dir, environment
        )

    assert runs["embedded"] == runs["exec"]
    assert runs["embedded"][0] == test_case.expected_exit_code, runs["embedded"]


@pytest.mark.parametrize(
    "test_case",
    [
        HostExitTestCase(
            description="success",
            exit_code=0,
            expected_run=(0, b"out 0\nerr 0\nout 1\nerr 1\nout 2\nerr 2\n", b""),
        ),
        HostExitTestCase(
            description="failure",
            exit_code=1,
            expected_run=(1, b"out 0\nerr 0\nout 1\nerr 1\nout 2\nerr 2\n", b""),
        ),
        HostExitTestCase(
            description="usage error",
            exit_code=2,
            expected_run=(2, b"out 0\nerr 0\nout 1\nerr 1\nout 2\nerr 2\n", b""),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_exit_status_when_hosting_then_streams_interleave_and_exit_as_exec(
    test_case: HostExitTestCase, tmp_path: Path
) -> None:
    probe: Path = write_host_probe(tmp_path / "probe")
    extra: dict[str, str] = {
        "PYTHONPATH": str(probe),
        PROBE_ACTION_VARIABLE: "streams",
        PROBE_EXIT_VARIABLE: str(test_case.exit_code),
    }

    runs: dict[str, HostedRun] = {
        mode: run_hosted_merged(
            NATIVE_SQB,
            ("--help",),
            tmp_path,
            host_environment(mode=mode, cache=tmp_path / "cache", extra=extra),
        )
        for mode in ("embedded", "exec")
    }

    assert runs["embedded"] == runs["exec"] == test_case.expected_run


@pytest.mark.parametrize(
    "test_case",
    [
        HostTracebackTestCase(
            description="uncaught runtime error",
            expected_exit_code=1,
            expected_stderr_start=b"Traceback (most recent call last):\n",
            expected_stderr_end=b"RuntimeError: host probe failure\n",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_uncaught_exception_when_hosting_then_python_prints_the_traceback_and_fails(
    test_case: HostTracebackTestCase, tmp_path: Path
) -> None:
    probe: Path = write_host_probe(tmp_path / "probe")
    extra: dict[str, str] = {"PYTHONPATH": str(probe), PROBE_ACTION_VARIABLE: "fail"}

    runs: dict[str, HostedRun] = {
        mode: run_hosted(
            NATIVE_SQB,
            ("--help",),
            tmp_path,
            host_environment(mode=mode, cache=tmp_path / "cache", extra=extra),
        )
        for mode in ("embedded", "exec")
    }

    assert runs["embedded"] == runs["exec"]
    assert runs["embedded"][:2] == (test_case.expected_exit_code, b"")
    assert runs["embedded"][2].startswith(test_case.expected_stderr_start), runs["embedded"]
    assert runs["embedded"][2].endswith(test_case.expected_stderr_end), runs["embedded"]


@pytest.mark.parametrize(
    "test_case",
    [
        HostInterruptTestCase(
            description="interrupt while the CLI runs",
            expected_exit_codes=(-signal.SIGINT, 130),
            expected_stderr_fragment=b"KeyboardInterrupt",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sigint_when_hosting_then_python_handles_it_as_exec_does(
    test_case: HostInterruptTestCase, tmp_path: Path
) -> None:
    probe: Path = write_host_probe(tmp_path / "probe")
    results: dict[str, HostedRun] = {}
    for mode in ("embedded", "exec"):
        extra: dict[str, str] = {
            "PYTHONPATH": str(probe),
            PROBE_ACTION_VARIABLE: "wait",
            PROBE_READY_VARIABLE: str(tmp_path / f"ready-{mode}"),
        }
        results[mode] = interrupt_hosted(
            NATIVE_SQB,
            cwd=tmp_path,
            environment=host_environment(mode=mode, cache=tmp_path / "cache", extra=extra),
        )

    assert results["embedded"][0] == results["exec"][0]
    assert results["embedded"][0] in test_case.expected_exit_codes, results["embedded"]
    assert test_case.expected_stderr_fragment in results["embedded"][2], results["embedded"]
    assert test_case.expected_stderr_fragment in results["exec"][2], results["exec"]


@pytest.mark.skipif(
    base_needs_shared_libpython(), reason="this interpreter needs a shared libpython to start"
)
@pytest.mark.parametrize(
    "test_case",
    [
        HostFallbackTestCase(
            description="copied base interpreter without its libpython",
            expected_report_prefix="exec (",
            expected_report_fragment="shared libpython",
            expected_cache_files=1,
            expected_required_exit_code=1,
            expected_required_error=(
                b"sqb: cannot start the SQLBuild Python CLI in this process: "
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_interpreter_without_shared_libpython_when_hosting_then_sqb_falls_back_to_exec(
    test_case: HostFallbackTestCase, tmp_path: Path
) -> None:
    program, extra_paths = host_install(
        tmp_path / "venv",
        interpreter=static_base(tmp_path / "base"),
        script_head=PLAIN_SCRIPT_HEAD,
        install_dependencies=dependencies_in_pth,
    )
    probe: Path = write_host_probe(tmp_path / "probe")
    extra: dict[str, str] = {
        "PYTHONPATH": os.pathsep.join([str(probe), *extra_paths]),
        PROBE_ACTION_VARIABLE: "describe",
    }
    cache: Path = tmp_path / "cache"

    automatic: HostedRun = run_hosted(
        program, ("--help",), tmp_path, host_environment(mode="", cache=cache, extra=extra)
    )
    cached: HostedRun = run_hosted(
        program, ("--help",), tmp_path, host_environment(mode="", cache=cache, extra=extra)
    )
    required: HostedRun = run_hosted(
        program, ("--help",), tmp_path, host_environment(mode="embedded", cache=cache, extra=extra)
    )

    assert automatic[0] == 0, automatic[2]
    report: str = str(json.loads(automatic[1])["host"])
    assert report.startswith(test_case.expected_report_prefix), report
    assert test_case.expected_report_fragment in report, report
    assert cached == automatic
    assert len(list(cache.glob("sqlbuild/interpreters/*"))) == test_case.expected_cache_files
    assert required[:2] == (test_case.expected_required_exit_code, b"")
    assert required[2].startswith(test_case.expected_required_error), required[2]


@pytest.mark.parametrize(
    "test_case",
    [
        HostReplayTestCase(
            description="text compile",
            args=("compile",),
            expected_python_starts=(1, 1),
            expected_notice=b"Inputs unchanged; reused the previous compile",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unchanged_project_when_hosting_embedded_then_sqb_replays_without_python(
    test_case: HostReplayTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "project")
    program, _ = host_install(
        tmp_path / "venv",
        interpreter=Path(sys.executable),
        script_head=PLAIN_SCRIPT_HEAD,
        install_dependencies=dependencies_in_pth,
    )
    probe: Path = write_host_probe(tmp_path / "probe")
    starts: Path = starts_log(tmp_path / "python-starts.log")
    environment: dict[str, str] = host_environment(
        mode="embedded",
        cache=tmp_path / "cache",
        extra={"PYTHONPATH": str(probe), PROBE_STARTS_VARIABLE: str(starts)},
    )

    first: HostedRun = run_hosted(program, test_case.args, project_dir, environment)
    after_first: int = python_starts(starts)
    served: HostedRun = run_hosted(program, test_case.args, project_dir, environment)

    assert (first[0], served[0]) == (0, 0), first[2] + served[2]
    assert (after_first, python_starts(starts)) == test_case.expected_python_starts
    assert served[2].startswith(test_case.expected_notice), served[2]
