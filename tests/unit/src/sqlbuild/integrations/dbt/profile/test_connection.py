from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild._native import resolve_raw_dbt_profile_connection
from sqlbuild.integrations.dbt.exceptions import DbtProfileError
from sqlbuild.integrations.dbt.models import NormalizedDbtProfileConnection
from tests.unit.src.sqlbuild.integrations.dbt.profile._test_types import (
    DbtProfileConnectionErrorTestCase,
    DbtProfileConnectionTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.profile.helpers import (
    dbt_workspace_project_config,
    write_duckdb_dbt_workspace,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtProfileConnectionTestCase(
            description="the project's dbt profile resolves to adapter config",
            raw_config={"source": "dbt_profile", "target": " dev "},
            adapter_name="duckdb",
            expected_connection={"database": "warehouse.duckdb"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_raw_connection_when_resolving_dbt_profile_then_returns_expected_connection(
    test_case: DbtProfileConnectionTestCase, tmp_path: Path
) -> None:
    write_duckdb_dbt_workspace(tmp_path)

    resolved: NormalizedDbtProfileConnection | None = resolve_raw_dbt_profile_connection(
        raw_config=test_case.raw_config,
        project_dir=tmp_path,
        adapter_name=test_case.adapter_name,
        project_config=dbt_workspace_project_config(adapter_name=test_case.adapter_name),
    )

    assert resolved is not None
    assert resolved.connection == test_case.expected_connection


@pytest.mark.parametrize(
    "test_case",
    [
        DbtProfileConnectionTestCase(
            description="a connection without the dbt_profile source is not resolved",
            raw_config={"database": "orders.duckdb"},
            adapter_name="duckdb",
            expected_connection=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_profile_connection_when_resolving_dbt_profile_then_returns_none(
    test_case: DbtProfileConnectionTestCase, tmp_path: Path
) -> None:
    resolved: NormalizedDbtProfileConnection | None = resolve_raw_dbt_profile_connection(
        raw_config=test_case.raw_config,
        project_dir=tmp_path,
        adapter_name=test_case.adapter_name,
        project_config=dbt_workspace_project_config(adapter_name=test_case.adapter_name),
    )

    assert resolved == test_case.expected_connection


@pytest.mark.parametrize(
    "test_case",
    [
        DbtProfileConnectionErrorTestCase(
            description="a blank profile name is rejected",
            raw_config={"source": "dbt_profile", "profile": "  "},
            adapter_name="duckdb",
            expected_error_fragment="dbt_profile connection values must be non-empty strings",
        ),
        DbtProfileConnectionErrorTestCase(
            description="a profile for another adapter is rejected",
            raw_config={"source": "dbt_profile"},
            adapter_name="snowflake",
            expected_error_fragment="dbt=duckdb, sqlbuild=snowflake",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_dbt_profile_reference_when_resolving_then_raises_profile_error(
    test_case: DbtProfileConnectionErrorTestCase, tmp_path: Path
) -> None:
    write_duckdb_dbt_workspace(tmp_path)

    with pytest.raises(DbtProfileError, match=test_case.expected_error_fragment) as captured:
        resolve_raw_dbt_profile_connection(
            raw_config=test_case.raw_config,
            project_dir=tmp_path,
            adapter_name=test_case.adapter_name,
            project_config=dbt_workspace_project_config(adapter_name=test_case.adapter_name),
        )

    assert captured.value.code == "C242"
