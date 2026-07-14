"""Stable constants for discovery helpers."""

from __future__ import annotations

import re

from sqlbuild.compiler.references.types import SqlReferenceKind

MODEL_HEADER_END_TOKEN: str = "end"
MODEL_HEADER_WORD_TOKEN: str = "word"
MODEL_HEADER_STRING_TOKEN: str = "string"
MODEL_HEADER_SYMBOL_TOKEN: str = "symbol"
MODEL_HEADER_SYMBOLS: frozenset[str] = frozenset({"(", ")", "[", "]", ","})
MODEL_HEADER_OPEN_PAREN: str = "("
MODEL_HEADER_CLOSE_PAREN: str = ")"
MODEL_HEADER_OPEN_BRACKET: str = "["
MODEL_HEADER_CLOSE_BRACKET: str = "]"
MODEL_HEADER_COMMA: str = ","
MODEL_HEADER_KEY_VALUE_SEPARATOR: str = ":"
MODEL_HEADER_QUOTE_NAMES: dict[str, str] = {"'": "single", '"': "double"}
MODEL_HEADER_ESCAPE_CHARACTER: str = "\\"
MODEL_HEADER_COLUMNS_KEY: str = "columns"
MODEL_HEADER_RELATION_CALL_NAMES: frozenset[str] = frozenset(
    {
        SqlReferenceKind.REF.function_name,
        SqlReferenceKind.SEED.function_name,
        SqlReferenceKind.SOURCE.function_name,
    }
)
MODEL_HEADER_SQL_HOOK_CALL: str = "sql"
MODEL_HEADER_HOOK_CALL_NAMES: frozenset[str] = frozenset({MODEL_HEADER_SQL_HOOK_CALL, "python"})
MODEL_HEADER_HOOK_FIELD_NAMES: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})
MODEL_HEADER_TRUE_VALUE: str = "true"
MODEL_HEADER_FALSE_VALUE: str = "false"
MODEL_HEADER_NULL_VALUE: str = "null"
SQL_IDENTIFIER_SEPARATOR: str = "_"
SQL_SELECT_KEYWORD: str = "SELECT"
SQL_UNION_KEYWORD: str = "UNION"
SQL_FROM_KEYWORD: str = "FROM"
SQL_SELECT_INITIAL: str = SQL_SELECT_KEYWORD[0]
SQL_UNION_INITIAL: str = SQL_UNION_KEYWORD[0]
SQL_FROM_INITIAL: str = SQL_FROM_KEYWORD[0]
SQL_UNION_LOWER_KEYWORD: str = SQL_UNION_KEYWORD.lower()
MODEL_HEADER_INTEGER_PATTERN: re.Pattern[str] = re.compile(r"^[+-]?\d+$")
MODEL_HEADER_FLOAT_PATTERN: re.Pattern[str] = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+)$")

MODEL_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*MODEL\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)

TEST_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*TEST\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)

TEST_HEADER_ONLY_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*TEST\s*\((?P<header>.*?)\)\s*;\s*",
    re.DOTALL | re.MULTILINE,
)

AUDIT_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*AUDIT\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)

AUDIT_HEADER_ONLY_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*AUDIT\s*\((?P<header>.*?)\)\s*;\s*",
    re.DOTALL | re.MULTILINE,
)

SCENARIO_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*SCENARIO\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)

FUNCTION_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*FUNCTION\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)\Z",
    re.DOTALL,
)
