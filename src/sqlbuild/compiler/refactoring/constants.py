"""Constants for project refactorings."""

from __future__ import annotations

import re

from sqlbuild.compiler.discovery.constants import STATEMENT_HEADER_BODY_PATTERN
from sqlbuild.compiler.refactoring.types import (
    HeaderTokenKind,
    RefactorOperation,
    SqlFileRole,
)

MODEL_KIND_PREFIX: str = "model:"
COLUMN_KIND_PREFIX: str = "column:"
SQL_SUFFIX: str = ".sql"
PATH_SEPARATOR: str = "/"
IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
REF_FUNCTION: str = "__ref"
REF_CALL_PATTERN: re.Pattern[str] = re.compile(
    r"^__ref\s*\(\s*(?P<quote>['\"])(?P<name>[^'\"]+)(?P=quote)\s*\)$"
)
RESOURCE_CALL_PATTERN: re.Pattern[str] = re.compile(
    r"^__(?P<kind>ref|source|seed)\s*\(\s*(?P<quote>['\"])(?P<name>[^'\"]+)(?P=quote)\s*\)$"
)
EMBEDDED_REF_PATTERN: re.Pattern[str] = re.compile(
    r"""__ref\s*\(\s*\\?['"](?P<name>[^'"\\]+)\\?['"]\s*\)"""
)
REF_FIXTURE_PREFIX: str = "__ref__"
EXPECTED_FIXTURE_PREFIX: str = "__expected__"
ASSERT_FIXTURE_PREFIX: str = "__assert__"
NON_CODE_PATTERN: str = (
    r"--[^\n]*(?:\n|\Z)"
    r"|/\*[\s\S]*?(?:\*/|\Z)"
    r"|'(?:''|[^'])*(?:'|\Z)"
    r'|"(?:""|[^"])*(?:"|\Z)'
)
IDENTIFIER_CHARACTERS: str = r"A-Za-z0-9_$"
PLACEHOLDER_PAD: str = "_"
GENERIC_PLACEHOLDER_KIND: str = "x"
ROOT_SCOPE: str = "root"
CTE_SCOPE_PREFIX: str = "cte:"
MIGRATE_FROM_KEY: str = "migrate_from"
MATERIALIZED_KEY: str = "materialized"
CURSOR_INPUTS_KEY: str = "cursor_inputs"
COLUMNS_KEY: str = "columns"
RELATIONSHIPS_AUDIT: str = "relationships"
RELATIONSHIPS_TO_KEY: str = "to"
RELATIONSHIPS_FIELD_KEY: str = "field"
COLUMN_VALUED_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "cursor",
        "unique_key",
        "updated_at",
        "check_columns",
        "merge_exclude_columns",
        "partition_by",
        "cluster_by",
        "observed_at",
        "row_diff_exclude_columns",
    }
)
HISTORY_MATERIALIZATIONS: frozenset[str] = frozenset({"incremental", "snapshot"})
MIGRATABLE_MATERIALIZATIONS: frozenset[str] = frozenset(
    {"table", "view", "incremental", "snapshot"}
)
COPIED_PROJECT_SUFFIXES: frozenset[str] = frozenset(
    {".sql", ".py", ".yml", ".yaml", ".toml", ".csv", ".json"}
)
IGNORED_PROJECT_DIRECTORIES: frozenset[str] = frozenset(
    {"target", "logs", "venv", "node_modules", "__pycache__"}
)
SQL_LIKE_PATTERN: re.Pattern[str] = re.compile(r"\b(select|from|join|insert|update)\b", re.I)
OPERATION_TITLES: dict[RefactorOperation, str] = {
    RefactorOperation.RENAME_MODEL: "Rename model",
    RefactorOperation.MOVE_MODEL: "Move model",
    RefactorOperation.RENAME_COLUMN: "Rename column",
}
PLACEHOLDER_BASE: str = "_q{kind}{index}"
QUOTE_CHARACTERS: dict[str, str] = {'"': '"', "`": "`", "[": "]"}
COLUMN_TARGET_SEPARATOR: str = "."
HEADER_OPENERS: frozenset[str] = frozenset({"(", "[", "{"})
HEADER_CLOSERS: frozenset[str] = frozenset({")", "]", "}"})
HEADER_SEPARATOR: str = ","
HEADER_OPEN_PAREN: str = "("
HEADER_DESCRIPTION_KEY: str = "description"
HEADER_INDENT: str = "  "
PARENTHESIZED_EMPTY_TOKENS: int = 2
REF_KIND: str = "ref"
FIXTURE_ROLES: frozenset[SqlFileRole] = frozenset({SqlFileRole.TEST, SqlFileRole.SCENARIO})
HIDDEN_PREFIX: str = "."
TEXT_ENCODING: str = "utf-8"
GENERIC_DIALECT: str = "generic"
NATIVE_HEADER_TOKEN_KINDS: dict[int, HeaderTokenKind] = {
    0: HeaderTokenKind.END,
    1: HeaderTokenKind.WORD,
    2: HeaderTokenKind.STRING,
    3: HeaderTokenKind.SYMBOL,
}
HEADER_KEY_AND_VALUE_TOKENS: int = 2
PYCACHE_DIRECTORY: str = "__pycache__"
SOURCE_KIND: str = "source"
SEED_KIND: str = "seed"
UNKNOWN_COLUMN_TYPE: str = "UNKNOWN"
MODEL_MANUAL_HELP: str = (
    "Pass the model into the macro as an argument, or edit the listed locations, then run the "
    "command again."
)
COLUMN_MANUAL_HELP: str = "Edit the listed locations, then run the command again."
SCHEMA_STATEMENT_PATTERN: re.Pattern[str] = re.compile(
    r"\bSCHEMA\s*\(" + STATEMENT_HEADER_BODY_PATTERN + r"\)\s*;"
)
