"""Stable constants for compile-time helpers."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.references.types import SqlReferenceKind

PRESERVE_TARGET_VALUE: str = "preserve"

AUDIT_DIRECTORY_NAME: str = "audits"
GENERIC_AUDIT_DIRECTORY_NAME: str = "generic"
NOT_NULL_AUDIT_NAME: str = "not_null"
MODEL_AUDIT_OVERRIDE_KEYS: frozenset[str] = frozenset({"by_type", "by_column"})
MODEL_HEADER_METADATA_KEYS: frozenset[str] = frozenset({"description", "columns", "audits"})

SQL_WILDCARD_TOKEN: str = "*"
SQL_OPEN_PAREN_TOKEN: str = "("
SQL_CLOSE_PAREN_TOKEN: str = ")"
SQL_ARGUMENT_SEPARATOR_TOKEN: str = ","
SQL_STATEMENT_TERMINATOR_TOKEN: str = ";"
SQL_SINGLE_QUOTE_TOKEN: str = "'"
SQL_QUOTE_TOKENS: frozenset[str] = frozenset({"'", '"', "`"})
SQL_REFERENCE_NAME_QUOTE_TOKENS: frozenset[str] = frozenset({"'", '"'})
SQL_IDENTIFIER_EXTRA_TOKEN: str = "_"
SQL_UNION_KEYWORD: str = "UNION"
SQL_UNION_ALL_KEYWORD: str = "ALL"
SQL_SET_OPERATION_KEYWORDS: tuple[str, ...] = ("UNION", "INTERSECT", "EXCEPT")
SQL_WITH_KEYWORD: str = "WITH"
SQL_CEREMONIAL_SELECT_VALUE: str = "1"
UNKNOWN_SQL_TYPE_NAME: str = "UNKNOWN"
DECIMAL_SQL_TYPE_NAME: str = "DECIMAL"
RESOLVED_SOURCE_CONFIDENCE: str = "resolved"
LEFT_JOIN_SIDE: str = "LEFT"
RIGHT_JOIN_SIDE: str = "RIGHT"
FULL_JOIN_SIDE: str = "FULL"

POLYGLOT_UNION_EXPRESSION_NAME: str = "Union"
POLYGLOT_SELECT_EXPRESSION_NAME: str = "Select"
POLYGLOT_COLUMN_EXPRESSION_NAME: str = "Column"
POLYGLOT_WRAPPER_EXPRESSION_NAMES: frozenset[str] = frozenset({"Subquery", "Paren"})

TABLE_FUNCTION_RETURN_KEYS: frozenset[str] = frozenset({"table"})

MACRO_TOKEN: str = "@"
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
TEMPLATE_FALSE_VALUES: frozenset[str] = frozenset({"", "0", "false"})
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
GENERIC_AUDIT_QUOTED_PARAMETER_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!@)@'(?P<name>[A-Za-z_][A-Za-z0-9_]*)'"
)
GENERIC_AUDIT_RAW_PARAMETER_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!@)@(?!')(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?!\s*\()"
)
EXPECTED_TEST_CTE_PREFIX: str = "__expected__"
ASSERT_TEST_CTE_PREFIX: str = "__assert__"
REF_TEST_CTE_PREFIX: str = SqlReferenceKind.REF.fixture_cte_prefix
SOURCE_TEST_CTE_PREFIX: str = SqlReferenceKind.SOURCE.fixture_cte_prefix
SEED_TEST_CTE_PREFIX: str = SqlReferenceKind.SEED.fixture_cte_prefix
DBT_REF_TEST_CTE_PREFIX: str = SqlReferenceKind.DBT_REF.fixture_cte_prefix
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
