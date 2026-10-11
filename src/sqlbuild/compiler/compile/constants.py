"""Stable constants for compile-time helpers."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile.classes.compile_input_read_registry import (
    CompileInputReadRegistry,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.references.types import SqlReferenceKind

PRESERVE_TARGET_VALUE: str = "preserve"

SINGULAR_AUDIT_NOT_CROSS_RESOURCE_CODE: str = "P004"
ATTACHED_AUDIT_READS_OWN_DEPENDANT_CODE: str = "P005"
MACRO_GENERATED_REFERENCE_CODE: str = "P006"
HOOK_READS_OWN_DEPENDANT_CODE: str = "P007"
HARD_CODED_PROJECT_RELATION_CODE: str = "P008"
UNNEEDED_SQL_ANALYSIS_OPT_OUT_CODE: str = "P009"
MISSING_DESCRIPTION_CODE: str = "P010"
CURSOR_MODEL_WITHOUT_INPUTS_CODE: str = "P011"
REFERENCE_CALL_SYNTAX_CODE: str = "P012"
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
SQL_ANALYSIS_OPT_OUT_ENTRY: str = "sql_analysis false"
HOOK_DIRECTORY_NAME: str = "hooks"
MODEL_DIRECTORY_NAME: str = "models"
NOT_NULL_AUDIT_NAME: str = "not_null"
MODEL_AUDIT_OVERRIDE_KEYS: frozenset[str] = frozenset({"by_type", "by_column"})
CURSOR_INPUTS_CONFIG_KEY: str = "cursor_inputs"
MIGRATE_FROM_CONFIG_KEY: str = "migrate_from"
MIGRATE_FORCE_CONFIG_KEY: str = "migrate_force"
COLUMN_MIGRATE_FROM_KEY: str = "migrate_from"
MAX_MICROBATCHES_CONFIG_KEY: str = "max_microbatches"
MODEL_HEADER_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "description",
        "columns",
        "dynamic_columns",
        "model_schema",
        "audits",
        "audit_factories",
        "enums",
        "constants",
    }
)

SQL_OPEN_PAREN_TOKEN: str = "("
SQL_ARGUMENT_SEPARATOR_TOKEN: str = ","
SQL_STATEMENT_TERMINATOR_TOKEN: str = ";"
SQL_QUOTE_TOKENS: frozenset[str] = frozenset({"'", '"', "`", "$"})
SQL_WITH_KEYWORD: str = "WITH"
SQL_CEREMONIAL_SELECT_VALUE: str = "1"
OMITTED_CEREMONIAL_SELECT_SQL: str = f"\nSELECT {SQL_CEREMONIAL_SELECT_VALUE}"


TABLE_FUNCTION_RETURN_KEYS: frozenset[str] = frozenset({"table"})

MACRO_TOKEN: str = "@"
DECLARATION_REFERENCE_NAMES: frozenset[str] = frozenset({"enum", "const"})
MACRO_CONTEXT_PARAMETER_NAME: str = "ctx"
MACRO_ARGUMENT_ERROR_TAG: str = "error"
MACRO_ARGUMENT_NESTED_CALL_TAG: str = "c"
SQL_INTERPOLATION_TOKEN: str = "@@"

TEMPLATE_OPEN_TOKEN: str = "${"

MACRO_CALL_PATTERN: re.Pattern[str] = re.compile(r"@[A-Za-z_][A-Za-z0-9_]*\s*\(")
SQL_ARGUMENT_QUOTED_PARAMETER_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!@)@'(?P<name>[A-Za-z_][A-Za-z0-9_]*)'"
)
SQL_ARGUMENT_RAW_PARAMETER_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!@)@(?!')(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?![A-Za-z0-9_])(?!\s*\()"
)
EXPECTED_TEST_CTE_PREFIX: str = "__expected__"
ASSERT_TEST_CTE_PREFIX: str = "__assert__"
REF_TEST_CTE_PREFIX: str = SqlReferenceKind.REF.fixture_cte_prefix
SOURCE_TEST_CTE_PREFIX: str = SqlReferenceKind.SOURCE.fixture_cte_prefix
SEED_TEST_CTE_PREFIX: str = SqlReferenceKind.SEED.fixture_cte_prefix
DBT_REF_TEST_CTE_PREFIX: str = SqlReferenceKind.DBT_REF.fixture_cte_prefix
TABLE_FN_TEST_CTE_PREFIX: str = SqlReferenceKind.TABLE_FUNCTION.fixture_cte_prefix
MACRO_TEST_CTE_PREFIX: str = "__macro__"
MACRO_ACTUAL_TEST_CTE_NAME: str = "__macro_actual__"
MACRO_EXPECTED_TEST_CTE_NAME: str = "__macro_expected__"
UDF_ACTUAL_TEST_CTE_NAME: str = "__udf_actual__"
UDF_EXPECTED_TEST_CTE_NAME: str = "__udf_expected__"
TABLE_FN_ACTUAL_TEST_CTE_NAME: str = "__table_fn_actual__"
TABLE_FN_EXPECTED_TEST_CTE_NAME: str = "__table_fn_expected__"
DEFAULT_SQL_TEST_MODE: SqlTestMode = SqlTestMode.MODEL
COMPILE_CACHE_DISABLE_ENV_VAR: str = "SQLBUILD_DISABLE_COMPILE_CACHE"
COMPILE_CACHE_DISABLE_VALUE: str = "1"
COMPILE_INPUT_READS: CompileInputReadRegistry = CompileInputReadRegistry()
SQL_TEST_SCAN_STORE_FILE_NAME: str = "sql-test-scans.bin"
RETIRED_FACT_CACHE_DIRECTORY_NAME: str = "facts-v1"
RETIRED_REFERENCE_CACHE_DIRECTORY_NAME: str = "references-v3"
SQL_TEST_SCAN_STORE_VERSION: str = "sql-test-scan-store-v1"
SQL_TEST_CTE_SCAN_ALGORITHM: str = "expanded-sql-test-ctes-v1"
SQL_TEST_EXPECTED_MODELS_SCAN_ALGORITHM: str = "sql-test-expected-models-v1"
