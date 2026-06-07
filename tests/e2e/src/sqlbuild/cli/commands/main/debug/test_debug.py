from __future__ import annotations

import json
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.debug._test_types import (
    DebugCliTestCase,
    DebugJsonCliTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)

DEBUG_CLI_TEST_CASES: list[DebugCliTestCase] = [
    DebugCliTestCase(
        description="checks duckdb connection by default",
        command=("debug",),
        expected_stdout_fragment=(
            "  connection test: [OK connected]\n  query test: [OK SELECT 1]\n"
        ),
    ),
    DebugCliTestCase(
        description="skips connection when requested",
        command=("debug", "--no-connection"),
        expected_stdout_fragment=(
            "  connection test: [SKIP skipped by --no-connection]\n"
            "  query test: [SKIP connection skipped]\n"
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DEBUG_CLI_TEST_CASES,
    ids=[case.description for case in DEBUG_CLI_TEST_CASES],
)
def test_given_debug_command_when_running_then_outputs_checks(
    tmp_path: Path,
    test_case: DebugCliTestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="debug_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "debug_project"\nadapter = "duckdb"\n\n'
                '[connection]\ndatabase = "debug.duckdb"\n'
            ),
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stderr
    assert result.stdout.startswith("\nSQLBuild Diagnostics\n\n")
    assert "Runtime:\n" in result.stdout
    assert "Configuration:\n" in result.stdout
    assert "Providers:\n" in result.stdout
    assert "Connection:\n" in result.stdout
    assert "  database: " in result.stdout
    assert test_case.expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DebugJsonCliTestCase(
            description="outputs machine readable skipped connection checks",
            command=("debug", "--json", "--no-connection"),
            expected_success=True,
            expected_check_tail=[
                {
                    "label": "connection test",
                    "message": "",
                    "status": "SKIP",
                    "status_message": "skipped by --no-connection",
                },
                {
                    "label": "query test",
                    "message": "",
                    "status": "SKIP",
                    "status_message": "connection skipped",
                },
            ],
        )
    ],
    ids=["outputs machine readable skipped connection checks"],
)
def test_given_debug_json_when_running_then_outputs_machine_readable_checks(
    tmp_path: Path,
    test_case: DebugJsonCliTestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="debug_json_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "debug_json_project"\nadapter = "duckdb"\n\n'
                '[connection]\ndatabase = "debug.duckdb"\n'
            ),
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr
    payload: dict[str, object] = json.loads(result.stdout)
    assert payload["success"] is test_case.expected_success
    connection: list[dict[str, str]] = payload["connection"]  # type: ignore[assignment]
    assert connection[-2:] == test_case.expected_check_tail


@pytest.mark.parametrize(
    "test_case",
    [
        DebugCliTestCase(
            description="reports discovered providers",
            command=("debug", "--no-connection"),
            expected_stdout_fragment=(
                "Providers:\n"
                "  providers: 1 [OK discovered]\n"
                "  marker_provider: providers/marker.py:MarkerProvider [OK valid settings]\n"
            ),
        )
    ],
    ids=["reports discovered providers"],
)
def test_given_debug_command_with_providers_when_running_then_outputs_provider_summary(
    tmp_path: Path,
    test_case: DebugCliTestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="debug_provider_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "debug_provider_project"\nadapter = "duckdb"\n\n'
                '[connection]\ndatabase = "debug_provider.duckdb"\n'
            ),
            "providers/marker.py": dedent(
                """
                from sqlbuild.providers import Provider


                class MarkerProvider(Provider):
                    label: str = "debug"
                """
            ).strip()
            + "\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stderr
    assert test_case.expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DebugJsonCliTestCase(
            description="reports discovered providers in json",
            command=("debug", "--json", "--no-connection"),
            expected_success=True,
            expected_check_tail=[
                {
                    "label": "providers",
                    "message": "1",
                    "status": "OK",
                    "status_message": "discovered",
                },
                {
                    "label": "marker_provider",
                    "message": "providers/marker.py:MarkerProvider",
                    "status": "OK",
                    "status_message": "valid settings",
                },
            ],
        )
    ],
    ids=["reports discovered providers in json"],
)
def test_given_debug_json_with_providers_when_running_then_outputs_provider_summary(
    tmp_path: Path,
    test_case: DebugJsonCliTestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="debug_provider_json_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "debug_provider_json_project"\nadapter = "duckdb"\n\n'
                '[connection]\ndatabase = "debug_provider_json.duckdb"\n'
            ),
            "providers/marker.py": dedent(
                """
                from sqlbuild.providers import Provider


                class MarkerProvider(Provider):
                    label: str = "debug"
                """
            ).strip()
            + "\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr
    payload: dict[str, object] = json.loads(result.stdout)
    assert payload["success"] is test_case.expected_success
    providers: list[dict[str, str]] = payload["providers"]  # type: ignore[assignment]
    assert providers == test_case.expected_check_tail
