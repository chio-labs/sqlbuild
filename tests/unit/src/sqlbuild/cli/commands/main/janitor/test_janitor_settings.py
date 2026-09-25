"""Tests for janitor settings resolution from discovered project config."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands._helpers.janitor_runtime.invocation import (
    resolve_janitor_invocation,
    resolve_janitor_settings,
)
from sqlbuild.cli.commands.models import (
    JanitorCommandRequest,
    JanitorInvocation,
    JanitorSettings,
)
from tests.unit.src.sqlbuild.cli.commands.main.janitor._test_types import (
    JanitorSettingsResolutionTestCase,
)

DIRECT_PROJECT_TOML: str = (
    'name = "orders_direct"\nadapter = "duckdb"\n\n[connection]\ndatabase = "orders.duckdb"\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorSettingsResolutionTestCase(
            description="direct mode without explicit retention resolves 14",
            project_toml=DIRECT_PROJECT_TOML + "\n[janitor]\nenabled = true\n",
            cli_retention_days=None,
            expected_retention_days=14,
            expected_archive_retention_days=14,
        ),
        JanitorSettingsResolutionTestCase(
            description="explicit retention applies to direct mode",
            project_toml=DIRECT_PROJECT_TOML
            + "\n[janitor]\nenabled = true\nretention_days = 9\narchive_retention_days = 2\n",
            cli_retention_days=None,
            expected_retention_days=9,
            expected_archive_retention_days=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_config_when_resolving_janitor_settings_then_uses_mode_specific_default(
    test_case: JanitorSettingsResolutionTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(test_case.project_toml, encoding="utf-8")
    request: JanitorCommandRequest = JanitorCommandRequest(
        project_dir=tmp_path, no_color=True, retention_days=test_case.cli_retention_days
    )

    invocation: JanitorInvocation = resolve_janitor_invocation(request=request)
    settings: JanitorSettings = resolve_janitor_settings(request=request, invocation=invocation)

    assert settings.retention_days == test_case.expected_retention_days
    assert settings.archive_retention_days == test_case.expected_archive_retention_days
