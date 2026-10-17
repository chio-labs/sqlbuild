"""Tests for debug process reporting and partial timings across failed native builds."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from sqlbuild._native import (
    BuildCommandRequest,
    CliUserError,
    ProviderDiscoveryError,
    run_build_command,
)
from tests.unit.src.sqlbuild.cli.commands.main.execution._test_types import (
    BuildDurationLimitTestCase,
    BuildProcessReportTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.execution.helpers import fail_build_discovery


@pytest.mark.parametrize(
    "test_case",
    [
        BuildProcessReportTestCase(
            description="failed debug build reports resources and partial timings",
            provider_source='raise RuntimeError("provider import failed")\n',
            error_type=ProviderDiscoveryError,
            verbose=False,
            expected_fragments=("Phase timings", "total"),
            expected_absent_fragments=("compile", "planning", "execution"),
        ),
        BuildProcessReportTestCase(
            description="interrupted debug build reports resources and partial timings",
            provider_source="raise KeyboardInterrupt\n",
            error_type=KeyboardInterrupt,
            verbose=True,
            expected_fragments=("Phase timings", "total"),
            expected_absent_fragments=("connection preparation",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failed_debug_build_when_unwinding_then_reports_resources_and_partial_timings(
    test_case: BuildProcessReportTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    reporter: Mock = fail_build_discovery(
        monkeypatch=monkeypatch, project_dir=tmp_path, provider_source=test_case.provider_source
    )

    with pytest.raises(test_case.error_type):
        run_build_command(
            request=BuildCommandRequest(project_dir=tmp_path, debug=True, verbose=test_case.verbose)
        )

    reporter.assert_called_once_with(enabled=True)
    errors: str = capsys.readouterr().err
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in errors
    for fragment in test_case.expected_absent_fragments:
        assert fragment not in errors


@pytest.mark.parametrize(
    "test_case",
    [
        BuildDurationLimitTestCase(
            description="DuckDB target cannot guarantee statement cancellation",
            project_toml=(
                'name = "shop"\nadapter = "duckdb"\ndefault_target = "dev"\n\n'
                '[targets.dev.execution_limits]\nmax_duration = "30m"\n'
            ),
            remediation="Use an adapter with safe statement cancellation.",
            expected_code="C415",
            expected_error_fragment="cannot cancel active statements safely",
        ),
        BuildDurationLimitTestCase(
            description="Snowflake target rejects duration beyond statement timeout range",
            project_toml=(
                'name = "shop"\nadapter = "snowflake"\ndefault_target = "dev"\n\n'
                '[targets.dev]\ndatabase = "analytics"\nschema = "dev"\n\n'
                '[targets.dev.execution_limits]\nmax_duration = "8d"\n'
            ),
            remediation="Choose a duration supported by the configured warehouse.",
            expected_code="C416",
            expected_error_fragment="max_duration exceeds the largest duration supported",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unenforceable_duration_limit_when_building_then_configuration_is_rejected(
    test_case: BuildDurationLimitTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        f'{test_case.project_toml}remediation = "{test_case.remediation}"\n', encoding="utf-8"
    )

    with pytest.raises(CliUserError) as raised:
        run_build_command(request=BuildCommandRequest(project_dir=tmp_path))

    assert raised.value.code == test_case.expected_code
    assert test_case.expected_error_fragment in raised.value.message
    assert raised.value.help == test_case.remediation


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
