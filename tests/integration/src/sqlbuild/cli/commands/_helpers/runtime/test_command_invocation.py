"""Integration tests for resolving CLI command invocations against a real DuckDB project."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sqlbuild.cli.commands import models as command_models
from sqlbuild.cli.commands._helpers.audit.invocation import resolve_audit_invocation
from sqlbuild.cli.commands._helpers.check.invocation import resolve_check_invocation
from sqlbuild.cli.commands._helpers.seed.invocation import resolve_seed_invocation
from sqlbuild.cli.commands._helpers.test.invocation import resolve_test_invocation
from tests.integration.src.sqlbuild.cli.commands._helpers.runtime._test_types import (
    CommandInvocationTestCase,
)

_PROJECT_TOML: str = (
    'name = "orders_shop"\nadapter = "duckdb"\n\n[connection]\ndatabase = "orders.duckdb"\n'
)


@pytest.mark.parametrize(
    "test_case",
    (
        CommandInvocationTestCase(
            description="audit json output reports progress on stderr",
            resolve=resolve_audit_invocation,
            request_type=command_models.AuditCommandRequest,
            json_output=True,
            expected_invocation_type_name="AuditInvocation",
            expected_stream_name="stderr",
            expected_has_progress_reporters=True,
        ),
        CommandInvocationTestCase(
            description="check text output reports progress on stdout",
            resolve=resolve_check_invocation,
            request_type=command_models.CheckCommandRequest,
            json_output=False,
            expected_invocation_type_name="CheckInvocation",
            expected_stream_name="stdout",
            expected_has_progress_reporters=True,
        ),
        CommandInvocationTestCase(
            description="test json output reports progress on stderr",
            resolve=resolve_test_invocation,
            request_type=command_models.TestCommandRequest,
            json_output=True,
            expected_invocation_type_name="TestInvocation",
            expected_stream_name="stderr",
            expected_has_progress_reporters=True,
        ),
        CommandInvocationTestCase(
            description="seed text output omits shared progress reporters",
            resolve=resolve_seed_invocation,
            request_type=command_models.SeedCommandRequest,
            json_output=False,
            expected_invocation_type_name="SeedInvocation",
            expected_stream_name="stdout",
            expected_has_progress_reporters=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_duckdb_project_when_resolving_command_invocation_then_returns_command_context(
    tmp_path: Path,
    test_case: CommandInvocationTestCase,
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(_PROJECT_TOML, encoding="utf-8")
    request: object = test_case.request_type(
        project_dir=tmp_path, no_color=True, json_output=test_case.json_output
    )

    invocation: (
        command_models.AuditInvocation
        | command_models.CheckInvocation
        | command_models.SeedInvocation
        | command_models.TestInvocation
    ) = test_case.resolve(request=request)

    assert type(invocation).__name__ == test_case.expected_invocation_type_name
    assert invocation.effective_project_dir == tmp_path
    assert invocation.adapter_name == "duckdb"
    assert invocation.discovered_inputs.project_config.name == "orders_shop"
    assert invocation.use_color is False
    assert invocation.progress_stream is getattr(sys, test_case.expected_stream_name)
    assert hasattr(invocation, "connection_progress") is test_case.expected_has_progress_reporters
    assert hasattr(invocation, "planning_progress") is test_case.expected_has_progress_reporters
