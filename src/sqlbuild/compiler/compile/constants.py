"""Stable constants for compile-time helpers."""

from __future__ import annotations

import re

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
}
SQL_ANALYSIS_OPT_OUT_ENTRY: str = "sql_analysis false"
HOOK_DIRECTORY_NAME: str = "hooks"
MODEL_DIRECTORY_NAME: str = "models"
NOT_NULL_AUDIT_NAME: str = "not_null"
MODEL_AUDIT_OVERRIDE_KEYS: frozenset[str] = frozenset({"by_type", "by_column"})
MODEL_FULL_REFRESH_CONFIG_KEY: str = "full_refresh"
CURSOR_INPUTS_CONFIG_KEY: str = "cursor_inputs"
MIGRATE_FROM_CONFIG_KEY: str = "migrate_from"
MIGRATE_FORCE_CONFIG_KEY: str = "migrate_force"
COLUMN_MIGRATE_FROM_KEY: str = "migrate_from"
MAX_MICROBATCHES_CONFIG_KEY: str = "max_microbatches"
MICROBATCH_LIMIT_MAX_BATCHES_KEY: str = "max_batches"
MICROBATCH_LIMIT_ACTION_KEY: str = "action"
WATERMARK_CURSOR_INPUT_BLOCK_KEYS: frozenset[str] = frozenset({"column", "roles"})
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

SQL_WILDCARD_TOKEN: str = "*"
SQL_OPEN_PAREN_TOKEN: str = "("
SQL_CLOSE_PAREN_TOKEN: str = ")"
SQL_ARGUMENT_SEPARATOR_TOKEN: str = ","
SQL_STATEMENT_TERMINATOR_TOKEN: str = ";"
SQL_SINGLE_QUOTE_TOKEN: str = "'"
SQL_QUOTE_TOKENS: frozenset[str] = frozenset({"'", '"', "`", "$"})
SQL_QUALIFIER_SEPARATOR_TOKEN: str = "."
SQL_REFERENCE_NAME_QUOTE_TOKENS: frozenset[str] = frozenset({"'", '"'})
SQL_IDENTIFIER_EXTRA_TOKEN: str = "_"
SQL_WITH_KEYWORD: str = "WITH"
SQL_CEREMONIAL_SELECT_VALUE: str = "1"
UNKNOWN_SQL_TYPE_NAME: str = "UNKNOWN"
DECIMAL_SQL_TYPE_NAME: str = "DECIMAL"
RESOLVED_SOURCE_CONFIDENCE: str = "resolved"

POLYGLOT_SET_OPERATION_EXPRESSION_NAMES: frozenset[str] = frozenset(
    {"Union", "Intersect", "Except"}
)
POLYGLOT_SELECT_EXPRESSION_NAME: str = "Select"
POLYGLOT_COLUMN_EXPRESSION_NAME: str = "Column"
POLYGLOT_WRAPPER_EXPRESSION_NAMES: frozenset[str] = frozenset({"Annotated", "Subquery", "Paren"})

TABLE_FUNCTION_RETURN_KEYS: frozenset[str] = frozenset({"table"})

MACRO_TOKEN: str = "@"
DECLARATION_REFERENCE_NAMES: frozenset[str] = frozenset({"enum", "const"})
MACRO_CONTEXT_PARAMETER_NAME: str = "ctx"
PYTHON_LITERAL_NAMES: frozenset[str] = frozenset({"True", "False", "None"})
SQL_INTERPOLATION_TOKEN: str = "@@"
SQL_CONTEXT_NAME_EXTRA_TOKENS: frozenset[str] = frozenset({"_", "."})

TEMPLATE_TRUE_LITERAL: str = "true"
TEMPLATE_FALSE_LITERAL: str = "false"
TEMPLATE_NULL_LITERAL: str = "null"
TEMPLATE_NAMESPACE_SEPARATOR: str = ":"
TEMPLATE_IF_FUNCTION_NAME: str = "if"
TEMPLATE_EQ_FUNCTION_NAME: str = "eq"
TEMPLATE_NE_FUNCTION_NAME: str = "ne"
TEMPLATE_COALESCE_FUNCTION_NAME: str = "coalesce"
TEMPLATE_ESCAPE_TOKEN: str = "\\"
TEMPLATE_OPEN_TOKEN: str = "${"
TEMPLATE_FALSE_VALUES: frozenset[str] = frozenset({"", "0", "false"})
POLYGLOT_LITERAL_KIND: str = "literal"
POLYGLOT_ARRAY_KIND: str = "array_func"
POLYGLOT_STRUCTURED_KINDS: frozenset[str] = frozenset({"parse_json", "struct"})
POLYGLOT_FUNCTION_KIND: str = "function"
MISSING_TEMPLATE_VALUE_MESSAGE_PARTS: frozenset[str] = frozenset(
    {
        "references missing ENV variable",
        "references unknown variable",
        "references unknown CTX key",
    }
)
MISSING_TEMPLATE_CONTEXT_MESSAGE_PART: str = "references CTX key"
MISSING_TEMPLATE_CONTEXT_VALUE_MESSAGE_PART: str = "no value is available"

TEMPLATE_PATTERN: re.Pattern[str] = re.compile(r"\$\{([^{}]+)\}")
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
ASSERT_SCENARIO_CTE_PREFIX: str = ASSERT_TEST_CTE_PREFIX
RESERVED_SQL_TEST_CTE_NAMES: frozenset[str] = frozenset(
    {
        "__actual",
        "__expected__typed",
        "__actual__projected",
        "__missing__",
        "__unexpected__",
    }
)
COMPILE_CACHE_DISABLE_ENV_VAR: str = "SQLBUILD_DISABLE_COMPILE_CACHE"
COMPILE_CACHE_DISABLE_VALUE: str = "1"
SQL_TEST_FACT_CACHE_NAMESPACE: str = "sql-tests"
SQL_TEST_FACT_CACHE_ALGORITHM: str = "expanded-sql-test-ctes-v2"
SQL_TEST_EXPECTED_MODELS_FACT_ALGORITHM: str = "sql-test-expected-models-v2"
COMPACT_ANALYSIS_RESPONSE_LENGTH: int = 2
COMPACT_RELATION_STUB_PREFIX: str = "__sqlbuild_project_input_"
COMPACT_REFERENCE_MARKER_PATTERN: re.Pattern[str] = re.compile(
    r'__(ref|seed|source|dbt_ref)\((?:"[^"]+"\s*,\s*)?"([^"]+)"\)'
)
COMPACT_UNSTUBBED_REFERENCE_KIND: str = "dbt_ref"
MIN_SHARED_BINDING_QUERY_MEMBERS: int = 2
COMPACT_ANALYSIS_LEGACY_RESPONSE_LENGTH: int = 3
COMPACT_ANALYSIS_FACT_LENGTH: int = 6
COMPACT_ANALYSIS_SOURCE_LENGTH: int = 3
MODEL_SCHEMA_CONFIG_KEY: str = "schema"
