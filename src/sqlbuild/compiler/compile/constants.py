"""Stable constants for compile-time helpers."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile.types import SqlReferenceKind

REF_CALL_NAME: str = f"__{SqlReferenceKind.REF.value}"
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
    r"@'(?P<name>[A-Za-z_][A-Za-z0-9_]*)'"
)
GENERIC_AUDIT_RAW_PARAMETER_PATTERN: re.Pattern[str] = re.compile(
    r"@(?!')(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?!\s*\()"
)
EXPECTED_TEST_CTE_PREFIX: str = "__expected__"
REF_TEST_CTE_PREFIX: str = "__ref__"
SOURCE_TEST_CTE_PREFIX: str = "__source__"
MACRO_TEST_CTE_PREFIX: str = "__macro__"
RESERVED_SQL_TEST_CTE_NAMES: frozenset[str] = frozenset(
    {
        "__actual",
        "__expected__typed",
        "__actual__projected",
        "__missing__",
        "__unexpected__",
    }
)
