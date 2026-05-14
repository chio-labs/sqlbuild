"""Stable constants for compile-time helpers."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile.types import SqlReferenceKind

REF_CALL_NAME: str = f"__{SqlReferenceKind.REF.value}"
SEED_CALL_NAME: str = f"__{SqlReferenceKind.SEED.value}"
SOURCE_CALL_NAME: str = f"__{SqlReferenceKind.SOURCE.value}"
DBT_REF_CALL_NAME: str = f"__{SqlReferenceKind.DBT_REF.value}"
UDF_CALL_NAME: str = f"__{SqlReferenceKind.UDF.value}"
TABLE_FUNCTION_CALL_NAME: str = f"__{SqlReferenceKind.TABLE_FUNCTION.value}"

PRESERVE_ENVIRONMENT_VALUE: str = "preserve"

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
REF_TEST_CTE_PREFIX: str = "__ref__"
SOURCE_TEST_CTE_PREFIX: str = "__source__"
SEED_TEST_CTE_PREFIX: str = "__seed__"
DBT_REF_TEST_CTE_PREFIX: str = "__dbt_ref__"
MACRO_TEST_CTE_PREFIX: str = "__macro__"
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
