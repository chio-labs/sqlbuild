import sys
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.entry._test_types import LaunchedTeardownTestCase
from tests.integration.src.sqlbuild.cli.entry.helpers import (
    PYTHON_CLI,
    LauncherRun,
    compile_timings,
    compiled_files,
    run,
    without_compile_timings,
    write_project,
)

IN_PROCESS_ENTRY: str = (
    "import sys\nfrom sqlbuild.cli.entry.main.entry import main\nsys.exit(main(sys.argv[1:]))\n"
)


@pytest.mark.parametrize(
    "test_case",
    [
        LaunchedTeardownTestCase(
            description="json report", args=("compile", "--json"), expected_hits=1
        )
    ],
    ids=lambda case: case.description,
)
def test_given_launched_cli_when_compiling_then_output_matches_entry_and_cache_is_reused(
    test_case: LaunchedTeardownTestCase, tmp_path: Path
) -> None:
    launched_dir: Path = write_project(tmp_path / "launched")
    entry_dir: Path = write_project(tmp_path / "entry")

    launched: LauncherRun = run(PYTHON_CLI, args=test_case.args, cwd=launched_dir)
    entry: LauncherRun = run(
        Path(sys.executable), args=("-c", IN_PROCESS_ENTRY, *test_case.args), cwd=entry_dir
    )
    repeated: LauncherRun = run(PYTHON_CLI, args=test_case.args, cwd=launched_dir)

    assert launched[0] == entry[0] == repeated[0] == 0
    assert without_compile_timings(launched[1]) == without_compile_timings(entry[1])
    assert compiled_files(launched_dir) == compiled_files(entry_dir)
    assert compiled_files(launched_dir)
    assert compile_timings(repeated[1])["project_reuse_hits"] == test_case.expected_hits
    assert without_compile_timings(repeated[1]) == without_compile_timings(launched[1])
