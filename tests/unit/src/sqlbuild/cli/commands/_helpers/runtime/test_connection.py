from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.adapter.types import BuiltinAdapter
from sqlbuild.cli.commands._helpers.runtime import connection as connection_core
from sqlbuild.cli.commands._helpers.runtime.connection import (
    resolve_connection_config,
    resolve_project_connection_config,
    resolve_target_connection_config,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.models import NormalizedDbtProfileConnection
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, TargetConfig
from tests.unit.src.sqlbuild.cli.commands._helpers.runtime._test_types import (
    ResolveConnectionConfigWarningTestCase,
    ResolveDbtProfileConnectionConfigTestCase,
    ResolveEnvironmentConnectionConfigTestCase,
    ResolveProjectConnectionConfigTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveProjectConnectionConfigTestCase(
            description="uses project target and local connection precedence",
            project_dir_name="demo_project",
            expected_connection={
                "database": "demo_project/local.duckdb",
                "warehouse": "dev_wh",
                "role": "local_role",
            },
            expected_warning_fragment=(
                "Warning: DuckDB adapter is active, but connection contains "
                "Snowflake-like keys: role, warehouse. If this is a Snowflake local config, "
                "add top-level `adapter: snowflake` to sqlbuild_local.toml."
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_inputs_when_resolving_connection_then_uses_effective_connection(
    test_case: ResolveProjectConnectionConfigTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = tmp_path / test_case.project_dir_name
    project_dir.mkdir()
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            default_target="dev",
            connection={"database": "project.duckdb", "warehouse": "project_wh"},
            targets={
                "dev": TargetConfig(connection={"database": "dev.duckdb", "warehouse": "dev_wh"})
            },
        ),
        local_config=LocalConfig(connection={"database": "local.duckdb", "role": "local_role"}),
    )

    connection: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )

    assert connection == {
        key: (
            str(tmp_path / value)
            if key == "database" and isinstance(value, str) and not value.startswith("/")
            else value
        )
        for key, value in test_case.expected_connection.items()
    }
    captured_err: str = capsys.readouterr().err
    assert test_case.expected_warning_fragment in captured_err


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveConnectionConfigWarningTestCase(
            description="does not warn when snowflake adapter has snowflake keys",
            raw_config={"database": "SQB_DB", "warehouse": "SQB_WH", "role": "SQB_ROLE"},
            adapter_name=BuiltinAdapter.SNOWFLAKE,
            expected_connection={
                "database": "SQB_DB",
                "warehouse": "SQB_WH",
                "role": "SQB_ROLE",
            },
            expected_warning="",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_connection_when_resolving_then_emits_expected_warning(
    test_case: ResolveConnectionConfigWarningTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    connection: dict[str, object] = resolve_connection_config(
        raw_config=test_case.raw_config,
        project_dir=tmp_path,
        adapter_name=test_case.adapter_name,
    )

    captured_err: str = capsys.readouterr().err
    assert connection == test_case.expected_connection
    assert captured_err == test_case.expected_warning


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveDbtProfileConnectionConfigTestCase(
            description="merges user connection overrides over resolved dbt profile connection",
            raw_config={
                "source": "dbt_profile",
                "profile": "analytics",
                "target": "dev",
                "profiles_dir": "../profiles",
                "account": "override-acct",
                "client_request_mfa_token": True,
            },
            profile_connection={
                "account": "profile-acct",
                "user": "analytics",
                "database": "RAW",
                "schema": "ANALYTICS",
            },
            expected_connection={
                "account": "override-acct",
                "user": "analytics",
                "database": "RAW",
                "schema": "ANALYTICS",
                "client_request_mfa_token": True,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_profile_connection_when_resolving_then_merges_user_overrides(
    test_case: ResolveDbtProfileConnectionConfigTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(name="demo", adapter="snowflake"),
        local_config=LocalConfig(),
    )

    def resolve_raw_dbt_profile_connection(**kwargs: object) -> NormalizedDbtProfileConnection:
        return NormalizedDbtProfileConnection(
            adapter=BuiltinAdapter.SNOWFLAKE.value,
            connection=test_case.profile_connection,
        )

    monkeypatch.setattr(
        connection_core,
        "resolve_raw_dbt_profile_connection",
        resolve_raw_dbt_profile_connection,
    )

    connection: dict[str, object] = resolve_connection_config(
        raw_config=test_case.raw_config,
        project_dir=tmp_path,
        adapter_name=BuiltinAdapter.SNOWFLAKE,
        discovered_inputs=discovered_inputs,
    )

    assert connection == test_case.expected_connection


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveEnvironmentConnectionConfigTestCase(
            description="resolves target connection with expanded env vars and local overrides",
            target_name="prod",
            expected_connection={
                "account": "test-account",
                "warehouse": "local_wh",
                "database": "analytics",
                "schema": "prod_schema",
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_target_connection_when_resolving_then_it_expands_effective_config(
    test_case: ResolveEnvironmentConnectionConfigTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_ACCOUNT", "test-account")
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="demo",
            adapter="snowflake",
            connection={
                "account": "${ENV:TEST_ACCOUNT}",
                "warehouse": "base_wh",
                "database": "analytics",
            },
            targets={
                "prod": TargetConfig(connection={"schema": "prod_schema"}),
            },
        ),
        local_config=LocalConfig(connection={"warehouse": "local_wh"}),
    )

    connection: dict[str, object] = resolve_target_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=tmp_path,
        target_name=test_case.target_name,
    )

    assert connection == test_case.expected_connection
