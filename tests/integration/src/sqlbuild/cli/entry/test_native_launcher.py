import sys
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.entry._test_types import (
    EditedProjectTestCase,
    HandoffTestCase,
    JsonReuseTestCase,
    PythonStartsTestCase,
    SelectorFileTestCase,
    TextReuseTestCase,
)
from tests.integration.src.sqlbuild.cli.entry.helpers import (
    NATIVE_SQB,
    PYTHON_CLI,
    LauncherRun,
    capture_metadata,
    compile_timings,
    compute_log_captures,
    counting_install,
    launch_records,
    python_starts,
    run,
    without_seconds,
    write_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        HandoffTestCase(description="version", args=("--version",), expected_exit_code=0),
        HandoffTestCase(description="help", args=("--help",), expected_exit_code=0),
        HandoffTestCase(
            description="unknown command", args=("not-a-command",), expected_exit_code=2
        ),
        HandoffTestCase(
            description="compile outside a project",
            args=("compile", "--json"),
            expected_exit_code=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_any_invocation_when_running_native_sqb_then_streams_and_exit_match_python(
    test_case: HandoffTestCase, tmp_path: Path
) -> None:
    native: LauncherRun = run(NATIVE_SQB, args=test_case.args, cwd=tmp_path)
    python: LauncherRun = run(PYTHON_CLI, args=test_case.args, cwd=tmp_path)

    assert native == python
    assert native[0] == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case",
    [
        TextReuseTestCase(
            description="text report",
            args=("compile",),
            expected_notice=b"Inputs unchanged; reused the previous compile (s)\n",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unchanged_project_when_compiling_again_then_sqb_replays_without_python(
    test_case: TextReuseTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "project")
    _ = run(NATIVE_SQB, args=test_case.args, cwd=project_dir)
    records: dict[Path, int] = launch_records(project_dir)
    captures: set[Path] = compute_log_captures(project_dir)

    served: LauncherRun = run(NATIVE_SQB, args=test_case.args, cwd=project_dir)
    (served_capture,) = compute_log_captures(project_dir) - captures
    python_hit: LauncherRun = run(PYTHON_CLI, args=test_case.args, cwd=project_dir)

    assert len(records) == 1
    assert launch_records(project_dir) == records, "a Python hit rewrites its launch record"
    assert served[0] == python_hit[0] == 0
    assert served[1] == python_hit[1]
    assert without_seconds(served[2]) == without_seconds(python_hit[2])
    assert without_seconds(served[2]).startswith(test_case.expected_notice)
    assert (served_capture / "stdout.log").read_bytes() == served[1]
    assert (served_capture / "stderr.log").read_bytes() == served[2]
    assert capture_metadata(served_capture) | {"started_at": None, "completed_at": None} == {
        **capture_metadata(served_capture),
        "started_at": None,
        "completed_at": None,
        "command": "compile",
        "exit_code": 0,
        "project_dir": str(project_dir.resolve()),
        "stdout_bytes": len(served[1]),
        "stderr_bytes": len(served[2]),
        "diagnostics_bytes": 0,
        "target": None,
        "run_id": None,
    }


@pytest.mark.parametrize(
    "test_case",
    [JsonReuseTestCase(description="json report", args=("compile", "--json"), expected_hits=1)],
    ids=lambda case: case.description,
)
def test_given_unchanged_project_when_compiling_json_again_then_sqb_reports_a_reuse_hit(
    test_case: JsonReuseTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "project")
    _ = run(NATIVE_SQB, args=test_case.args, cwd=project_dir)
    records: dict[Path, int] = launch_records(project_dir)

    served: LauncherRun = run(NATIVE_SQB, args=test_case.args, cwd=project_dir)
    python_hit: LauncherRun = run(PYTHON_CLI, args=test_case.args, cwd=project_dir)

    assert launch_records(project_dir) == records
    assert compile_timings(served[1])["project_reuse_hits"] == test_case.expected_hits
    assert compile_timings(served[1]).keys() == compile_timings(python_hit[1]).keys()
    assert served[1].replace(b" ", b"").count(b'_ms":') == python_hit[1].replace(b" ", b"").count(
        b'_ms":'
    )


@pytest.mark.parametrize(
    "test_case",
    [
        EditedProjectTestCase(
            description="added column",
            args=("compile", "--json"),
            old_text="1 AS order_id",
            new_text="2 AS order_id, 3 AS units",
            expected_misses=1,
            expected_fragment="units",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_edited_model_when_compiling_through_sqb_then_python_recompiles_the_change(
    test_case: EditedProjectTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "project")
    _ = run(NATIVE_SQB, args=test_case.args, cwd=project_dir)
    model: Path = project_dir / "models" / "orders.sql"
    _ = model.write_text(
        model.read_text(encoding="utf-8").replace(test_case.old_text, test_case.new_text),
        encoding="utf-8",
    )

    edited: LauncherRun = run(NATIVE_SQB, args=test_case.args, cwd=project_dir)

    assert edited[0] == 0
    assert compile_timings(edited[1])["project_reuse_misses"] == test_case.expected_misses
    assert test_case.expected_fragment in edited[1].decode()


@pytest.mark.parametrize(
    "test_case",
    [SelectorFileTestCase(description="orders", selectors="orders\n", expected_records=0)],
    ids=lambda case: case.description,
)
def test_given_selector_file_when_compiling_through_sqb_then_no_launch_record_is_left(
    test_case: SelectorFileTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "project")
    selectors: Path = tmp_path / "selectors.txt"
    _ = selectors.write_text(test_case.selectors, encoding="utf-8")
    args: tuple[str, ...] = ("compile", "--select-file", str(selectors))

    first: LauncherRun = run(NATIVE_SQB, args=args, cwd=project_dir)
    second: LauncherRun = run(NATIVE_SQB, args=args, cwd=project_dir)

    assert first[0] == second[0] == 0
    assert len(launch_records(project_dir)) == test_case.expected_records


@pytest.mark.skipif(sys.platform == "win32", reason="the logging handoff is a POSIX shell script")
@pytest.mark.parametrize(
    "test_case",
    [
        PythonStartsTestCase(
            description="text compile",
            args=("compile",),
            expected_python_starts=(1, 1, 2),
        ),
        PythonStartsTestCase(
            description="json compile",
            args=("compile", "--json"),
            expected_python_starts=(1, 1, 2),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unchanged_project_when_sqb_serves_the_hit_then_python_never_starts(
    test_case: PythonStartsTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "project")
    marker: Path = tmp_path / "python-starts.log"
    program: Path = counting_install(tmp_path / "bin", marker)

    first: LauncherRun = run(program, args=test_case.args, cwd=project_dir)
    after_first: int = python_starts(marker)
    served: LauncherRun = run(program, args=test_case.args, cwd=project_dir)
    after_served: int = python_starts(marker)
    model: Path = project_dir / "models" / "orders.sql"
    _ = model.write_text(
        model.read_text(encoding="utf-8").replace("1 AS order_id", "2 AS order_id"),
        encoding="utf-8",
    )
    edited: LauncherRun = run(program, args=test_case.args, cwd=project_dir)

    assert (first[0], served[0], edited[0]) == (0, 0, 0)
    assert without_seconds(served[2]).startswith(b"Inputs unchanged; reused the previous compile")
    assert (after_first, after_served, python_starts(marker)) == test_case.expected_python_starts
