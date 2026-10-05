"""Fresh-process guard that CLI startup loads only what the invoked command needs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    StartupImportFootprintTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import (
    write_compile_startup_project,
)

WAREHOUSE_AND_INTEGRATION_MODULES: tuple[str, ...] = (
    "dagster",
    "databricks",
    "dlt",
    "duckdb",
    "google.cloud.bigquery",
    "ingestr",
    "jinja2",
    "psycopg",
    "pyarrow",
    "pymssql",
    "snowflake.connector",
)
COMPILE_ONLY_MODULES: tuple[str, ...] = (
    "filelock",
    "polyglot_sql",
    "pydantic",
    "yaml",
    "sqlbuild._native",
    "sqlbuild.adapter.contract.classes.base_adapter",
    "sqlbuild.cli.compile.models",
    "sqlbuild.cli.output.models",
    "sqlbuild.compiler.compile.models",
    "sqlbuild.compiler.discovery.models",
    "sqlbuild.compiler.planner.models",
    "sqlbuild.lint",
    "sqlbuild.rule_engine",
    "sqlbuild.runtime.compute_logs",
)
PRESENTATION_AND_PROVIDER_MODULES: tuple[str, ...] = (
    "pydantic_settings",
    "rich",
    "sqlbuild.cli.commands.models",
)
PARSE_ONLY_FORBIDDEN: tuple[str, ...] = (
    *WAREHOUSE_AND_INTEGRATION_MODULES,
    *COMPILE_ONLY_MODULES,
    *PRESENTATION_AND_PROVIDER_MODULES,
)
COMPILE_FORBIDDEN: tuple[str, ...] = (
    *WAREHOUSE_AND_INTEGRATION_MODULES,
    *PRESENTATION_AND_PROVIDER_MODULES,
)

_FOOTPRINT_SCRIPT: str = """
import contextlib, io, json, sys
from sqlbuild.cli.entry.main.entry import main

argv = json.loads(sys.argv[1])
forbidden = json.loads(sys.argv[2])
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    code = main(argv)
loaded = sorted(
    name for name in forbidden
    if any(module == name or module.startswith(name + ".") for module in sys.modules)
)
print(json.dumps({"code": code, "loaded": loaded}))
"""


@pytest.mark.parametrize(
    "test_case",
    [
        StartupImportFootprintTestCase(
            description="version",
            argv=("--version",),
            expected_exit_code=0,
            forbidden_modules=PARSE_ONLY_FORBIDDEN,
        ),
        StartupImportFootprintTestCase(
            description="root help",
            argv=("--help",),
            expected_exit_code=0,
            forbidden_modules=PARSE_ONLY_FORBIDDEN,
        ),
        StartupImportFootprintTestCase(
            description="compile help",
            argv=("compile", "--help"),
            expected_exit_code=0,
            forbidden_modules=PARSE_ONLY_FORBIDDEN,
        ),
        StartupImportFootprintTestCase(
            description="unknown argument",
            argv=("compile", "--unknown-option"),
            expected_exit_code=2,
            forbidden_modules=PARSE_ONLY_FORBIDDEN,
        ),
        StartupImportFootprintTestCase(
            description="plain compile",
            argv=("compile", "--json"),
            expected_exit_code=0,
            forbidden_modules=COMPILE_FORBIDDEN,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fresh_interpreter_when_running_cli_then_heavy_modules_stay_unloaded(
    test_case: StartupImportFootprintTestCase, tmp_path: Path
) -> None:
    write_compile_startup_project(tmp_path)
    argv: list[str] = ["--project-dir", str(tmp_path), *test_case.argv]

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            sys.executable,
            "-c",
            _FOOTPRINT_SCRIPT,
            json.dumps(argv),
            json.dumps(test_case.forbidden_modules),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    outcome: dict[str, object] = json.loads(result.stdout.strip().splitlines()[-1])

    assert outcome["code"] == test_case.expected_exit_code
    assert cast(list[str], outcome["loaded"]) == []


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
