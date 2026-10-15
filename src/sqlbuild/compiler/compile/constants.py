"""Stable constants for compile-time helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.python_nodes.types import SqlResourceRefKind

UNNEEDED_SQL_ANALYSIS_OPT_OUT_CODE: str = "P009"
SQL_TEST_HELPER_REFERENCE_CODE: str = "P013"
DESCRIPTION_REQUIRED_INPUT_KINDS: dict[str, str] = {
    "model_files": "model",
    "scenario_files": "scenario",
    "seed_files": "seed",
    "source_files": "source",
    "sql_function_files": "function",
    "python_function_files": "function",
    "sql_hook_files": "hook",
    "hook_functions": "hook",
    "loader_functions": "loader",
    "task_functions": "task",
    "asset_functions": "asset",
    "check_functions": "check",
    "providers": "provider",
}
DESCRIPTION_EXEMPT_INPUTS: dict[str, str] = {
    "project_config": "project configuration, not a named resource",
    "local_config": "local configuration, not a named resource",
    "project_dir": "project location, not a named resource",
    "adapter_file": "project adapter override, not a named resource",
    "enum_files": "typed value declarations used inside SQL, not graph resources",
    "constant_files": "typed value declarations used inside SQL, not graph resources",
    "macro_files": "SQL helpers expanded inline, not graph resources",
    "model_schema_files": "shared column schemas; models that use one are checked",
    "schema_files": "seed YAML declarations; each declared seed is checked",
    "test_files": "SQL unit tests are named by their subject and expected behaviour",
    "audit_files": "audits are assertions named by what they check",
    "audit_factories": "generate audits, which are assertions",
    "materialization_files": "materialization strategies, not graph resources",
    "event_exporters": "runtime event outputs, not graph resources",
    "command_output_sinks": "runtime command outputs, not graph resources",
    "native_session": "native parse state kept for later stages, not a project input",
}
MIGRATE_FROM_CONFIG_KEY: str = "migrate_from"


MACRO_CONTEXT_PARAMETER_NAME: str = "ctx"


EXPECTED_TEST_CTE_PREFIX: str = "__expected__"
ASSERT_TEST_CTE_PREFIX: str = "__assert__"
REF_TEST_CTE_PREFIX: str = SqlReferenceKind.REF.fixture_cte_prefix
SOURCE_TEST_CTE_PREFIX: str = SqlReferenceKind.SOURCE.fixture_cte_prefix
SEED_TEST_CTE_PREFIX: str = SqlReferenceKind.SEED.fixture_cte_prefix
DBT_REF_TEST_CTE_PREFIX: str = SqlReferenceKind.DBT_REF.fixture_cte_prefix
TABLE_FN_TEST_CTE_PREFIX: str = SqlReferenceKind.TABLE_FUNCTION.fixture_cte_prefix
DEFAULT_SQL_TEST_MODE: SqlTestMode = SqlTestMode.MODEL
COMPILE_CACHE_DISABLE_ENV_VAR: str = "SQLBUILD_DISABLE_COMPILE_CACHE"
COMPILE_CACHE_DISABLE_VALUE: str = "1"
RETIRED_FACT_CACHE_DIRECTORY_NAME: str = "facts-v1"
RETIRED_REFERENCE_CACHE_DIRECTORY_NAME: str = "references-v3"
SQL_TEST_CTE_SCAN_ALGORITHM: str = "expanded-sql-test-ctes-v1"
SQL_TEST_EXPECTED_MODELS_SCAN_ALGORITHM: str = "sql-test-expected-models-v1"
EXPLICIT_REFERENCE_KINDS: dict[str, SqlResourceRefKind] = {
    SqlReferenceKind.REF.value: SqlResourceRefKind.MODEL,
    SqlReferenceKind.SOURCE.value: SqlResourceRefKind.SOURCE,
    SqlReferenceKind.SEED.value: SqlResourceRefKind.SEED,
}
