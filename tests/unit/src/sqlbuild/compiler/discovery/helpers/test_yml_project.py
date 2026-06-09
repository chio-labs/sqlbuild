from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.helpers.yml_project import (
    load_local_config,
    load_project_config,
)
from tests.unit.src.sqlbuild.compiler.discovery.helpers._test_types import (
    LoadLocalConfigErrorTestCase,
    LoadLocalConfigTestCase,
    LoadProjectConfigErrorTestCase,
    LoadProjectConfigTestCase,
)

LOCAL_CONFIG_TEST_CASES: list[LoadLocalConfigTestCase] = [
    LoadLocalConfigTestCase(
        description="defaults cleanly when local file is missing",
        repo_files={},
        expected_target=None,
        expected_adapter=None,
        expected_connection={},
        expected_sql_analysis=True,
        expected_sql_validation=True,
        expected_max_concurrency=1,
        expected_setting_overrides=frozenset(),
        expected_vars={},
    ),
    LoadLocalConfigTestCase(
        description="loads environment connection settings and vars from local config",
        repo_files={
            "sqlbuild_local.toml": """
target = "dev"
adapter = "snowflake"

[connection]
database = "local.duckdb"

[settings]
sql_analysis = false
sql_validation = false
concurrency = 4
auto_load_sources = false

[vars]
user = "kevin"

[scenario.local_type_overrides.snowflake]
"NUMBER(*,0)" = "BIGINT"
OBJECT = "JSON"

[scenario.snapshot_limits]
max_rows_per_relation = 12
max_total_rows = 34
max_bytes_per_relation = 56
max_total_bytes = 78
""".strip()
        },
        expected_target="dev",
        expected_adapter="snowflake",
        expected_connection={"database": "local.duckdb"},
        expected_sql_analysis=False,
        expected_sql_validation=False,
        expected_max_concurrency=4,
        expected_auto_load_sources=False,
        expected_setting_overrides=frozenset(
            {"sql_analysis", "sql_validation", "concurrency", "auto_load_sources"}
        ),
        expected_vars={"user": "kevin"},
        expected_scenario_local_type_overrides={
            "snowflake": {
                "NUMBER(*,0)": "BIGINT",
                "OBJECT": "JSON",
            }
        },
        expected_snapshot_limits={
            "max_rows_per_relation": 12,
            "max_total_rows": 34,
            "max_bytes_per_relation": 56,
            "max_total_bytes": 78,
        },
    ),
    LoadLocalConfigTestCase(
        description="loads legacy local max concurrency as canonical concurrency override",
        repo_files={
            "sqlbuild_local.toml": """
[settings]
max_concurrency = 4
""".strip()
        },
        expected_target=None,
        expected_adapter=None,
        expected_connection={},
        expected_sql_analysis=True,
        expected_sql_validation=True,
        expected_max_concurrency=4,
        expected_setting_overrides=frozenset({"concurrency"}),
        expected_vars={},
    ),
    LoadLocalConfigTestCase(
        description="does not expose unsupported project level overrides",
        repo_files={
            "sqlbuild_local.toml": """
default_target = "prod"

[defaults]
materialized = "table"

[janitor]
enabled = true

[connection]
database = "local.duckdb"
""".strip()
        },
        expected_target=None,
        expected_adapter=None,
        expected_connection={"database": "local.duckdb"},
        expected_sql_analysis=True,
        expected_sql_validation=True,
        expected_max_concurrency=1,
        expected_setting_overrides=frozenset(),
        expected_vars={},
        expected_missing_attributes=(
            "default_target",
            "defaults",
            "janitor",
        ),
    ),
    LoadLocalConfigTestCase(
        description="loads local target overrides",
        repo_files={
            "sqlbuild_local.toml": """
target = "dev"

[targets.dev]
database = "local_db"
schema = "local_schema"
defer_sources_to = "prod"
reuse_from = "prod"
reuse_hard_copy = true

[targets.dev.connection]
warehouse = "local_wh"

[targets.dev.vars]
user = "local_user"

[targets.dev.clone]
allow_as_source = true
allow_as_target = false
""".strip()
        },
        expected_target="dev",
        expected_adapter=None,
        expected_connection={},
        expected_sql_analysis=True,
        expected_sql_validation=True,
        expected_max_concurrency=1,
        expected_setting_overrides=frozenset(),
        expected_vars={},
        expected_targets={
            "dev": {
                "connection": {"warehouse": "local_wh"},
                "vars": {"user": "local_user"},
                "database": "local_db",
                "schema": "local_schema",
                "defer_sources_to": "prod",
                "reuse_from": "prod",
                "reuse_hard_copy": True,
                "allow_as_source": True,
                "allow_as_target": False,
            }
        },
    ),
]

PROJECT_CONFIG_ERROR_TEST_CASES: list[LoadProjectConfigErrorTestCase] = [
    LoadProjectConfigErrorTestCase(
        description="raises when virtual environments setting is not a boolean",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[settings]
virtual_environments = "yes"
""".strip(),
        expected_error_fragment="Expected 'virtual_environments' to be a boolean when provided",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when settings sql_analysis is not a boolean",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[settings]
sql_analysis = 123
""".strip(),
        expected_error_fragment="Expected 'sql_analysis' to be a boolean when provided",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when target reuse_from is not a string",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[targets.dev]
reuse_from = 123
""".strip(),
        expected_error_fragment="Expected 'reuse_from' to be a non-empty string when provided",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when target reuse_hard_copy is not a boolean",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[targets.dev]
reuse_hard_copy = "yes"
""".strip(),
        expected_error_fragment="Expected 'reuse_hard_copy' to be a boolean when provided",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when settings concurrency is not an integer",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[settings]
concurrency = "nope"
""".strip(),
        expected_error_fragment="Expected 'concurrency' to be an integer when provided",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when canonical and legacy concurrency settings are both provided",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[settings]
concurrency = 4
max_concurrency = 8
""".strip(),
        expected_error_fragment=(
            "settings cannot define both 'concurrency' and legacy 'max_concurrency'"
        ),
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when defaults batch_size has unsupported type",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[defaults.batch_size]
amount = 1
""".strip(),
        expected_error_fragment="Expected 'batch_size' to be a string or integer when provided",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when defaults contract is unknown",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[defaults]
contract = "strict"
""".strip(),
        expected_error_fragment="Expected 'contract' to be one of",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when snapshot current state full refresh policy is unknown",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[snapshots]
current_state_full_refresh = "force"
""".strip(),
        expected_error_fragment="Expected 'current_state_full_refresh' to be one of",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when snapshot historical full refresh policy is not string",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[snapshots]
historical_full_refresh = true
""".strip(),
        expected_error_fragment="Expected 'historical_full_refresh' to be a string",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when snapshot schema change policy is unknown",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[snapshots]
schema_change = "sync_all_columns"
""".strip(),
        expected_error_fragment="Expected 'schema_change' to be one of",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when path defaults child value is not a mapping",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[path_defaults]
staging = "view"
""".strip(),
        expected_error_fragment="path_defaults",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when project vars contain non string value",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[vars]
user = 123
""".strip(),
        expected_error_fragment="expected string value for 'user'",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when connection is not a mapping",
        project_file_contents="""
name = "demo"
adapter = "duckdb"
connection = "bad"
""".strip(),
        expected_error_fragment="Expected 'connection' to be a mapping when provided",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when environments is not a mapping",
        project_file_contents="""
name = "demo"
adapter = "duckdb"
targets = []
""".strip(),
        expected_error_fragment="targets must be a mapping",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when one environment entry is not a mapping",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[targets]
dev = "here"
""".strip(),
        expected_error_fragment="targets.dev must be a mapping",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when environment clone config is not a mapping",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[targets.dev]
clone = "nope"
""".strip(),
        expected_error_fragment="targets.dev.clone must be a mapping",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when environment vars contain non string value",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[targets.dev.vars]
user = false
""".strip(),
        expected_error_fragment="expected string value for 'user'",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when environment connection is not a mapping",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[targets.dev]
connection = "no"
""".strip(),
        expected_error_fragment="Expected 'connection' to be a mapping when provided",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when environment clone allow_as_source is not a boolean",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[targets.dev.clone]
allow_as_source = 123
""".strip(),
        expected_error_fragment="Expected 'allow_as_source' to be a boolean when provided",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when defaults tags is a string instead of list",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[defaults]
tags = "nightly"
""".strip(),
        expected_error_fragment="defaults.tags",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when path_defaults tags is a string instead of list",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[path_defaults."models/staging"]
tags = "staging"
""".strip(),
        expected_error_fragment="path_defaults.*tags must be a list",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when path_defaults tags contains non-string entry",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[path_defaults."models/staging"]
tags = [123]
""".strip(),
        expected_error_fragment="path_defaults.*tags.*must be strings",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when path defaults key has leading slash",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[path_defaults."/staging"]
schema = "staging"
""".strip(),
        expected_error_fragment="without a leading slash",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when path defaults key has empty path segment",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[path_defaults."staging//nested"]
schema = "staging"
""".strip(),
        expected_error_fragment="empty path segments",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when path defaults uses redundant models prefix",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[path_defaults."models/staging"]
schema = "staging"
""".strip(),
        expected_error_fragment="uses redundant 'models/' prefix",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when tracked-only janitor is enabled without query tracking",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[settings]
query_change_tracking = false

[janitor]
enabled = true
""".strip(),
        expected_error_fragment="janitor.delete_tracked_only requires",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when janitor max checkpoints is less than one",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[janitor]
max_checkpoints = 0
""".strip(),
        expected_error_fragment="janitor.max_checkpoints must be >= 1",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when project settings contain unknown key",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[settings]
threads = 4
""".strip(),
        expected_error_fragment=r"settings contains unknown key\(s\): threads",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when scenario snapshot limit is not an integer",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[scenario.snapshot_limits]
max_rows_per_relation = "many"
""".strip(),
        expected_error_fragment="Expected 'max_rows_per_relation' to be an integer when provided",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when scenario snapshot limit is negative",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[scenario.snapshot_limits]
max_total_bytes = -1
""".strip(),
        expected_error_fragment="scenario.snapshot_limits values must be >= 0",
    ),
    LoadProjectConfigErrorTestCase(
        description="raises when dbt config contains unknown key",
        project_file_contents="""
name = "demo"
adapter = "duckdb"

[dbt]
project_dir = "../dbt"
threads = 8
""".strip(),
        expected_error_fragment=r"dbt contains unknown key\(s\): threads",
    ),
]

LOCAL_CONFIG_ERROR_TEST_CASES: list[LoadLocalConfigErrorTestCase] = [
    LoadLocalConfigErrorTestCase(
        description="raises when local target is not a non empty string",
        local_file_contents="target = 123\n",
        expected_error_fragment="Expected 'target' to be a non-empty string when provided",
    ),
    LoadLocalConfigErrorTestCase(
        description="raises when local vars contain non string value",
        local_file_contents="""
[vars]
user = 123
""".strip(),
        expected_error_fragment="expected string value for 'user'",
    ),
    LoadLocalConfigErrorTestCase(
        description="raises when local connection is not a mapping",
        local_file_contents='connection = "local.duckdb"\n',
        expected_error_fragment="Expected 'connection' to be a mapping when provided",
    ),
    LoadLocalConfigErrorTestCase(
        description="raises when local settings sql_analysis is not a boolean",
        local_file_contents="""
[settings]
sql_analysis = "no thanks"
""".strip(),
        expected_error_fragment="Expected 'sql_analysis' to be a boolean when provided",
    ),
    LoadLocalConfigErrorTestCase(
        description="raises when local target reuse_from is not a string",
        local_file_contents="""
[targets.dev]
reuse_from = 123
""".strip(),
        expected_error_fragment="Expected 'reuse_from' to be a non-empty string when provided",
    ),
    LoadLocalConfigErrorTestCase(
        description="raises when local target reuse_hard_copy is not a boolean",
        local_file_contents="""
[targets.dev]
reuse_hard_copy = "yes"
""".strip(),
        expected_error_fragment="Expected 'reuse_hard_copy' to be a boolean when provided",
    ),
    LoadLocalConfigErrorTestCase(
        description="raises when local settings concurrency is not an integer",
        local_file_contents="""
[settings]
concurrency = "many"
""".strip(),
        expected_error_fragment="Expected 'concurrency' to be an integer when provided",
    ),
    LoadLocalConfigErrorTestCase(
        description="raises when local settings contain unknown key",
        local_file_contents="""
[settings]
extra_concurrency = 8
""".strip(),
        expected_error_fragment=r"settings contains unknown key\(s\): extra_concurrency",
    ),
]


PROJECT_CONFIG_TEST_CASES: list[LoadProjectConfigTestCase] = [
    LoadProjectConfigTestCase(
        description="defaults environment mode to direct when omitted",
        project_file_contents="""
name = "demo"
adapter = "duckdb"
default_target = "dev"

[targets.dev]
schema = "dev"
""".strip(),
        expected_name="demo",
        expected_adapter="duckdb",
        expected_default_target="dev",
        expected_connection={},
        expected_sql_analysis=True,
        expected_max_concurrency=1,
        expected_materialized=None,
        expected_row_diff_exclude_columns=(),
        expected_row_diff_tolerances={},
        expected_contract=None,
        expected_path_defaults={},
        expected_vars={},
        expected_targets={
            "dev": {
                "connection": {},
                "vars": {},
                "database": None,
                "schema": "dev",
                "defer_sources_to": None,
                "reuse_from": None,
                "reuse_hard_copy": False,
                "allow_as_source": False,
                "allow_as_target": False,
            }
        },
        expected_janitor_enabled=False,
        expected_retention_days=30,
        expected_janitor_max_checkpoints=20,
        expected_janitor_delete_tracked_only=True,
        expected_janitor_exclude_patterns=(),
    ),
    LoadProjectConfigTestCase(
        description="loads expected fields from project config",
        project_file_contents="""
name = "demo"
adapter = "duckdb"
default_target = "dev"

[connection]
path = "data.db"

[settings]
virtual_environments = true
sql_analysis = false
query_change_tracking = true
concurrency = 8
auto_load_sources = false

[defaults]
materialized = "table"
row_diff_exclude_columns = ["loaded_at"]
contract = "enforced"

[defaults.row_diff_tolerances.by_type.float]
relative = 0.0001
absolute = 0.000001

[defaults.row_diff_tolerances.by_column.revenue]
absolute = 0.01

[path_defaults.staging]
schema = "staging"

[vars]
user = "kevin"

[targets.dev]
schema = "dev_${user}"
defer_sources_to = "prod"
reuse_from = "prod"
reuse_hard_copy = true

[targets.dev.connection]
warehouse = "dev_wh"

[targets.dev.vars]
schema_prefix = "dev"

[targets.dev.clone]
allow_as_source = true
allow_as_target = true

[janitor]
enabled = true
retention_days = 14
max_checkpoints = 3
delete_tracked_only = false
exclude_patterns = ["partition_*"]

[snapshots]
current_state_full_refresh = "require_confirmation"
historical_full_refresh = "allow"
schema_change = "deny"
wildcard_check_schema_change = "append_new_columns"

[scenario.local_type_overrides.snowflake]
"NUMBER(*,0)" = "BIGINT"
OBJECT = "JSON"

[scenario.local_type_overrides.bigquery]
"BIGNUMERIC(*,*)" = "DECIMAL({1}, {2})"

[scenario.snapshot_limits]
max_rows_per_relation = 100
max_total_rows = 200
max_bytes_per_relation = 300
max_total_bytes = 400

[dbt]
project_dir = "../dbt"
profiles_dir = "../profiles"
target = "prod"
target_path = "target/dbt"
""".strip(),
        expected_name="demo",
        expected_adapter="duckdb",
        expected_virtual_environments=True,
        expected_default_target="dev",
        expected_connection={"path": "data.db"},
        expected_sql_analysis=False,
        expected_max_concurrency=8,
        expected_auto_load_sources=False,
        expected_materialized="table",
        expected_row_diff_exclude_columns=("loaded_at",),
        expected_row_diff_tolerances={
            "by_type": {
                "float": {"relative": 0.0001, "absolute": 0.000001},
            },
            "by_column": {
                "revenue": {"absolute": 0.01},
            },
        },
        expected_contract="enforced",
        expected_path_defaults={"staging": {"schema": "staging"}},
        expected_vars={"user": "kevin"},
        expected_targets={
            "dev": {
                "connection": {"warehouse": "dev_wh"},
                "vars": {"schema_prefix": "dev"},
                "database": None,
                "schema": "dev_${user}",
                "defer_sources_to": "prod",
                "reuse_from": "prod",
                "reuse_hard_copy": True,
                "allow_as_source": True,
                "allow_as_target": True,
            }
        },
        expected_janitor_enabled=True,
        expected_retention_days=14,
        expected_janitor_max_checkpoints=3,
        expected_janitor_delete_tracked_only=False,
        expected_janitor_exclude_patterns=("partition_*",),
        expected_current_state_full_refresh="require_confirmation",
        expected_historical_full_refresh="allow",
        expected_snapshot_schema_change="deny",
        expected_wildcard_check_schema_change="append_new_columns",
        expected_scenario_local_type_overrides={
            "snowflake": {
                "NUMBER(*,0)": "BIGINT",
                "OBJECT": "JSON",
            },
            "bigquery": {"BIGNUMERIC(*,*)": "DECIMAL({1}, {2})"},
        },
        expected_snapshot_limits={
            "max_rows_per_relation": 100,
            "max_total_rows": 200,
            "max_bytes_per_relation": 300,
            "max_total_bytes": 400,
        },
        expected_dbt_project_dir="../dbt",
        expected_dbt_profiles_dir="../profiles",
        expected_dbt_target="prod",
        expected_dbt_target_path="target/dbt",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PROJECT_CONFIG_TEST_CASES,
    ids=[case.description for case in PROJECT_CONFIG_TEST_CASES],
)
def test_given_project_config_file_when_loading_project_config_then_it_returns_expected_fields(
    test_case: LoadProjectConfigTestCase,
    tmp_path: Path,
) -> None:
    project_file: Path = tmp_path / "sqlbuild_project.toml"
    project_file.write_text(test_case.project_file_contents, encoding="utf-8")

    config: object = load_project_config(project_dir=tmp_path)

    assert config.name == test_case.expected_name
    assert config.adapter == test_case.expected_adapter
    assert config.settings.virtual_environments is test_case.expected_virtual_environments
    assert config.default_target == test_case.expected_default_target
    assert config.connection == test_case.expected_connection
    assert config.settings.sql_analysis is test_case.expected_sql_analysis
    assert config.settings.concurrency == test_case.expected_max_concurrency
    assert config.settings.auto_load_sources is test_case.expected_auto_load_sources
    assert config.defaults.materialized == test_case.expected_materialized
    assert config.defaults.row_diff_exclude_columns == test_case.expected_row_diff_exclude_columns
    assert config.defaults.row_diff_tolerances == test_case.expected_row_diff_tolerances
    assert config.defaults.contract == test_case.expected_contract
    assert config.path_defaults == test_case.expected_path_defaults
    assert config.vars == test_case.expected_vars
    assert {
        target_name: {
            "connection": target_config.connection,
            "vars": target_config.vars,
            "database": target_config.database,
            "schema": target_config.schema,
            "defer_sources_to": target_config.defer_sources_to,
            "reuse_from": target_config.reuse_from,
            "reuse_hard_copy": target_config.reuse_hard_copy,
            "allow_as_source": target_config.clone.allow_as_source,
            "allow_as_target": target_config.clone.allow_as_target,
        }
        for target_name, target_config in config.targets.items()
    } == test_case.expected_targets
    assert config.janitor.enabled is test_case.expected_janitor_enabled
    assert config.janitor.retention_days == test_case.expected_retention_days
    assert config.janitor.max_checkpoints == test_case.expected_janitor_max_checkpoints
    assert config.janitor.delete_tracked_only is test_case.expected_janitor_delete_tracked_only
    assert config.janitor.exclude_patterns == test_case.expected_janitor_exclude_patterns
    assert (
        config.snapshots.current_state_full_refresh == test_case.expected_current_state_full_refresh
    )
    assert config.snapshots.historical_full_refresh == test_case.expected_historical_full_refresh
    assert config.snapshots.schema_change == test_case.expected_snapshot_schema_change
    assert (
        config.snapshots.wildcard_check_schema_change
        == test_case.expected_wildcard_check_schema_change
    )
    assert config.scenario.local_type_overrides == test_case.expected_scenario_local_type_overrides
    assert {
        "max_rows_per_relation": config.scenario.snapshot_limits.max_rows_per_relation,
        "max_total_rows": config.scenario.snapshot_limits.max_total_rows,
        "max_bytes_per_relation": config.scenario.snapshot_limits.max_bytes_per_relation,
        "max_total_bytes": config.scenario.snapshot_limits.max_total_bytes,
    } == test_case.expected_snapshot_limits
    assert config.dbt.project_dir == test_case.expected_dbt_project_dir
    assert config.dbt.profiles_dir == test_case.expected_dbt_profiles_dir
    assert config.dbt.target == test_case.expected_dbt_target
    assert config.dbt.target_path == test_case.expected_dbt_target_path


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

    assert config.target == test_case.expected_target
    assert config.adapter == test_case.expected_adapter
    assert config.connection == test_case.expected_connection
    assert config.settings.sql_analysis is test_case.expected_sql_analysis
    assert config.settings.sql_validation is test_case.expected_sql_validation
    assert config.settings.concurrency == test_case.expected_max_concurrency
    assert config.settings.auto_load_sources is test_case.expected_auto_load_sources
    assert config.setting_overrides == test_case.expected_setting_overrides
    assert config.vars == test_case.expected_vars
    assert config.scenario.local_type_overrides == test_case.expected_scenario_local_type_overrides
    assert {
        "max_rows_per_relation": config.scenario.snapshot_limits.max_rows_per_relation,
        "max_total_rows": config.scenario.snapshot_limits.max_total_rows,
        "max_bytes_per_relation": config.scenario.snapshot_limits.max_bytes_per_relation,
        "max_total_bytes": config.scenario.snapshot_limits.max_total_bytes,
    } == test_case.expected_snapshot_limits
    assert {
        target_name: {
            "connection": target_config.connection,
            "vars": target_config.vars,
            "database": target_config.database,
            "schema": target_config.schema,
            "defer_sources_to": target_config.defer_sources_to,
            "reuse_from": target_config.reuse_from,
            "reuse_hard_copy": target_config.reuse_hard_copy,
            "allow_as_source": target_config.clone.allow_as_source,
            "allow_as_target": target_config.clone.allow_as_target,
        }
        for target_name, target_config in config.targets.items()
    } == test_case.expected_targets
    attribute_name: str
    for attribute_name in test_case.expected_missing_attributes:
        assert not hasattr(config, attribute_name)


@pytest.mark.parametrize(
    "test_case",
    PROJECT_CONFIG_ERROR_TEST_CASES,
    ids=[case.description for case in PROJECT_CONFIG_ERROR_TEST_CASES],
)
def test_given_invalid_project_config_file_when_loading_project_config_then_it_raises_clear_errors(
    test_case: LoadProjectConfigErrorTestCase,
    tmp_path: Path,
) -> None:
    project_file: Path = tmp_path / "sqlbuild_project.toml"
    project_file.write_text(test_case.project_file_contents, encoding="utf-8")

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        load_project_config(project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    [
        LoadProjectConfigErrorTestCase(
            description="raises clear error when project config is missing",
            project_file_contents="",
            expected_error_fragment="Project config not found",
        ),
    ],
    ids=["raises clear error when project config is missing"],
)
def test_given_missing_project_config_file_when_loading_project_config_then_it_raises_clear_error(
    test_case: LoadProjectConfigErrorTestCase,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        load_project_config(project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    [
        LoadProjectConfigErrorTestCase(
            description="raises clear error when legacy project config is present",
            project_file_contents="name: demo\nadapter: duckdb\n",
            expected_error_fragment="sqlbuild_project.yml is no longer supported",
        )
    ],
    ids=["raises clear error when legacy project config is present"],
)
def test_given_legacy_project_config_file_when_loading_project_config_then_it_raises_clear_error(
    test_case: LoadProjectConfigErrorTestCase,
    tmp_path: Path,
) -> None:
    project_file: Path = tmp_path / "sqlbuild_project.yml"
    project_file.write_text(test_case.project_file_contents, encoding="utf-8")

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        load_project_config(project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    LOCAL_CONFIG_ERROR_TEST_CASES,
    ids=[case.description for case in LOCAL_CONFIG_ERROR_TEST_CASES],
)
def test_given_invalid_local_config_file_when_loading_local_config_then_it_raises_clear_errors(
    test_case: LoadLocalConfigErrorTestCase,
    tmp_path: Path,
) -> None:
    local_file: Path = tmp_path / "sqlbuild_local.toml"
    local_file.write_text(test_case.local_file_contents, encoding="utf-8")

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        load_local_config(project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    [
        LoadLocalConfigErrorTestCase(
            description="raises clear error when legacy local config is present",
            local_file_contents="environment: dev\n",
            expected_error_fragment="sqlbuild_local.yml is no longer supported",
        )
    ],
    ids=["raises clear error when legacy local config is present"],
)
def test_given_legacy_local_config_file_when_loading_local_config_then_it_raises_clear_error(
    test_case: LoadLocalConfigErrorTestCase,
    tmp_path: Path,
) -> None:
    local_file: Path = tmp_path / "sqlbuild_local.yml"
    local_file.write_text(test_case.local_file_contents, encoding="utf-8")

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        load_local_config(project_dir=tmp_path)
