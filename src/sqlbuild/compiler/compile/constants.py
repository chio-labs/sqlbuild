"""Stable constants for compile-time helpers."""

from __future__ import annotations

import re

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
RESERVED_SQL_TEST_CTE_NAMES: frozenset[str] = frozenset(
    {
        "__actual",
        "__expected__typed",
        "__actual__projected",
        "__missing__",
        "__unexpected__",
    }
)
