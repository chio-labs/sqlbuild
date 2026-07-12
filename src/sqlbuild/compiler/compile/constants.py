"""Stable constants for compile-time helpers."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.references.types import SqlReferenceKind

PRESERVE_TARGET_VALUE: str = "preserve"

AUDIT_DIRECTORY_NAME: str = "audits"
GENERIC_AUDIT_DIRECTORY_NAME: str = "generic"

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
