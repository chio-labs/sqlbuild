"""Compile command import footprint in a fresh interpreter."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from tests.unit.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompileImportFootprintTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.compile.helpers import (
    prepare_static_compile_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CompileImportFootprintTestCase(
            description="compile skips build and execution command models",
            checked_modules=(
                "sqlbuild.cli.commands.models",
                "sqlbuild.executor.build.models",
                "sqlbuild.executor.run.models",
            ),
            expected_exit_code=0,
            expected_loaded_modules=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_local_project_when_compiling_in_fresh_process_then_command_models_stay_unloaded(
    test_case: CompileImportFootprintTestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_static_compile_project(tmp_path)
    script: str = (
        "import contextlib, io, json, sys\n"
        "from sqlbuild.cli.entry.main.entry import main\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        f"    code = main(['--project-dir', {str(project_dir)!r}, 'compile', '--json'])\n"
        f"names = {test_case.checked_modules!r}\n"
        "print(json.dumps({'code': code, "
        "'loaded': [name for name in names if name in sys.modules]}))\n"
    )

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-c", script], check=True, capture_output=True, text=True
    )
    outcome: dict[str, object] = json.loads(result.stdout.strip().splitlines()[-1])

    assert outcome["code"] == test_case.expected_exit_code
    assert tuple(cast(list[str], outcome["loaded"])) == test_case.expected_loaded_modules
