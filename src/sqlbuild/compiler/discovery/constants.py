"""Public discovery constants."""

from __future__ import annotations

PROJECT_CONFIG_FILENAME: str = "sqlbuild_project.toml"
LOCAL_CONFIG_FILENAME: str = "sqlbuild_local.toml"
LEGACY_PROJECT_CONFIG_FILENAME: str = "sqlbuild_project.yml"
LEGACY_LOCAL_CONFIG_FILENAME: str = "sqlbuild_local.yml"
TOML_FILE_SUFFIX: str = ".toml"
SCHEMA_FILE_NAME: str = "schema.yml"
SEED_FILE_SUFFIX: str = ".csv"
YAML_FILE_SUFFIXES: frozenset[str] = frozenset({".yml", ".yaml"})
RESERVED_MODEL_NAMES: frozenset[str] = frozenset({"_chain_"})

PYTHON_INIT_MODULE_STEM: str = "__init__"
PYTHON_LOADER_FOLDER: str = "loaders"
PYTHON_FACTORY_FOLDER: str = "factories"
PYTHON_NODE_KIND_VOWELS: frozenset[str] = frozenset({"a", "e", "i", "o", "u"})
PYTHON_UDF_DECORATOR_NAME: str = "udf"
PYTHON_UDF_IMPORT_MODULES: frozenset[str] = frozenset({"sqlbuild", "sqlbuild.functions"})

DLT_LOADER_KIND: str = "dlt"
DLT_SOURCE_TYPE_SQL_DATABASE: str = "sql_database"
DLT_SOURCE_TYPE_REST_API: str = "rest_api"
DLT_SOURCE_TYPE_FILESYSTEM: str = "filesystem"
DLT_SOURCE_TYPES: frozenset[str] = frozenset(
    {DLT_SOURCE_TYPE_SQL_DATABASE, DLT_SOURCE_TYPE_REST_API, DLT_SOURCE_TYPE_FILESYSTEM}
)
DLT_RESOURCE_WRITE_STRATEGY_KEY: str = "write_strategy"
DLT_WRITE_DISPOSITION_DELETE_INSERT: str = "delete_insert"
DLT_WRITE_DISPOSITION_MERGE: str = "merge"

CONFIG_CONCURRENCY_KEY: str = "concurrency"
LEGACY_CONFIG_CONCURRENCY_KEY: str = "max_concurrency"
SQL_ANALYSIS_SETTING_KEY: str = "sql_analysis"
DBT_LEGACY_REUSE_FROM_CONFIG_KEY: str = "reuse_from"
DBT_DEFER_CLONE_CONFIG_KEY: str = "defer_clone_from"
DBT_REPLAY_ON_CHANGE_CONFIG_KEY: str = "replay_on_change"
SOURCE_LOADER_CONFIG_KEY: str = "loader"
SOURCE_AGE_POLICY_CONFIG_KEY: str = "age_policy"

MODELS_DIRECTORY_NAME: str = "models"
SEEDS_DIRECTORY_NAME: str = "seeds"
DBT_MACRO_PATH_PREFIX: tuple[str, str] = ("dbt", "macros")
PARENT_DIRECTORY_PATH_PART: str = ".."
CURRENT_DIRECTORY_PATH: str = "."

NOT_NULL_AUDIT_NAME: str = "not_null"
SOURCE_FRESHNESS_DURATION_UNITS: frozenset[str] = frozenset({"m", "h", "d"})
SOURCE_FRESHNESS_DAY_UNIT: str = "d"
SOURCE_FRESHNESS_HOUR_UNIT: str = "h"
