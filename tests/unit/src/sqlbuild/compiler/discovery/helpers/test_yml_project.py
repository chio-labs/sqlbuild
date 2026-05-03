from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.helpers.yml_project import (
    load_local_config,
    load_project_config,
)
from tests.unit.src.sqlbuild.compiler.discovery.helpers._test_types import (
    LoadLocalConfigTestCase,
    LoadProjectConfigTestCase,
)

LOCAL_CONFIG_TEST_CASES: list[LoadLocalConfigTestCase] = [
    LoadLocalConfigTestCase(
        description="defaults cleanly when local file is missing",
        repo_files={},
        expected_environment=None,
        expected_vars={},
    ),
    LoadLocalConfigTestCase(
        description="loads environment and vars from local config",
        repo_files={
            "sqlbuild_local.yml": """
environment: dev
vars:
  user: kevin
""".strip()
        },
        expected_environment="dev",
        expected_vars={"user": "kevin"},
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        LoadProjectConfigTestCase(
            description="loads expected fields from project config",
            project_file_contents="""
name: demo
adapter: duckdb
default_environment: dev

connection:
  path: data.db

settings:
  sqlglot: false
  query_change_tracking: true

defaults:
  materialized: table
  row_diff_exclude_columns:
    - loaded_at

path_defaults:
  models/staging:
    schema: staging

vars:
  user: kevin

environments:
  dev:
    connection:
      warehouse: dev_wh
    vars:
      schema_prefix: dev
    schema: "dev_${user}"
    clone:
      allow_as_source: true
      allow_as_target: true

janitor:
  retention_days: 14
""".strip(),
            expected_name="demo",
            expected_adapter="duckdb",
            expected_default_environment="dev",
            expected_connection={"path": "data.db"},
            expected_sqlglot=False,
            expected_materialized="table",
            expected_row_diff_exclude_columns=("loaded_at",),
            expected_path_default_schema="staging",
            expected_vars={"user": "kevin"},
            expected_dev_connection={"warehouse": "dev_wh"},
            expected_dev_vars={"schema_prefix": "dev"},
            expected_dev_schema="dev_${user}",
            expected_allow_as_source=True,
            expected_retention_days=14,
        )
    ],
    ids=["loads expected fields from project config"],
)
def test_given_project_config_file_when_loading_project_config_then_it_returns_expected_fields(
    test_case: LoadProjectConfigTestCase,
    tmp_path: Path,
) -> None:
    project_file: Path = tmp_path / "sqlbuild_project.yml"
    project_file.write_text(test_case.project_file_contents, encoding="utf-8")

    config: object = load_project_config(project_dir=tmp_path)

    assert config.name == test_case.expected_name
    assert config.adapter == test_case.expected_adapter
    assert config.default_environment == test_case.expected_default_environment
    assert config.connection == test_case.expected_connection
    assert config.settings.sqlglot is test_case.expected_sqlglot
    assert config.defaults.materialized == test_case.expected_materialized
    assert config.defaults.row_diff_exclude_columns == test_case.expected_row_diff_exclude_columns
    assert (
        config.path_defaults["models/staging"]["schema"] == test_case.expected_path_default_schema
    )
    assert config.vars == test_case.expected_vars
    assert config.environments["dev"].connection == test_case.expected_dev_connection
    assert config.environments["dev"].vars == test_case.expected_dev_vars
    assert config.environments["dev"].schema == test_case.expected_dev_schema
    assert config.environments["dev"].clone.allow_as_source is test_case.expected_allow_as_source
    assert config.janitor.retention_days == test_case.expected_retention_days


@pytest.mark.parametrize(
    "test_case",
    LOCAL_CONFIG_TEST_CASES,
    ids=[case.description for case in LOCAL_CONFIG_TEST_CASES],
)
def test_given_local_config_state_when_loading_local_config_then_it_returns_expected_fields(
    test_case: LoadLocalConfigTestCase,
    tmp_path: Path,
) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in test_case.repo_files.items():
        file_path: Path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")

    config: object = load_local_config(project_dir=tmp_path)

    assert config.environment == test_case.expected_environment
    assert config.vars == test_case.expected_vars
