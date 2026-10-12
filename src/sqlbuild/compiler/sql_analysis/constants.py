"""Polyglot SQL analysis vocabulary."""

from __future__ import annotations

SQL_ESCAPABLE_QUOTE_CHARACTERS: frozenset[str] = frozenset({"'", '"'})
SQL_ESCAPE_CHARACTER: str = "\\"
SQL_TRIPLE_QUOTE_LENGTH: int = 3
SQL_LINE_COMMENT_PREFIX: str = "--"
SUPPORTED_SQL_LINE_COMMENT_PREFIXES: frozenset[str] = frozenset({"--", "//", "#"})
SQL_BLOCK_COMMENT_OPEN: str = "/*"
SNOWFLAKE_DIALECT_NAME: str = "snowflake"
POLYGLOT_ANALYZE_QUERY_ENTRY_POINT: str = "analyze_query"
POLYGLOT_ANALYZE_QUERY_OPTIONS_ARGUMENT_COUNT: int = 2
POLYGLOT_ANALYZE_QUERY_OPTIONS_ARGUMENT_INDEX: int = 1
POLYGLOT_COMPLEXITY_GUARD_PARAMETER: str = "complexity_guard"
POLYGLOT_COMPLEXITY_GUARD_OPTION: str = "complexityGuard"
POLYGLOT_MAX_FUNCTION_CALL_DEPTH_OPTION: str = "maxFunctionCallDepth"
POLYGLOT_MAX_FUNCTION_CALL_DEPTH: int = 512
BINDING_UNKNOWN_TABLE_INTERNAL_CODE: str = "B000"

TYPE_CHECKED_DIALECTS: frozenset[str] = frozenset({"duckdb", "snowflake", "postgresql", "bigquery"})
SQL_QUOTED_IDENTIFIER_DELIMITER: str = '"'
CASE_SENSITIVE_BINDING_DIALECTS: frozenset[str] = frozenset({"snowflake", "postgresql"})
NATIVE_DIALECT_ALIASES: dict[str, str] = {
    "postgres": "postgresql",
    "motherduck": "duckdb",
    "sqlserver": "tsql",
}
ANALYSIS_NORMALIZATION_CHUNK_SIZE: int = 256
TABLE_FUNCTION_ANALYSIS_PREFIX: str = "__sqlbuild_table_function_"
NATIVE_FAILURE_PREFIX: str = "NativeCompilerError: "
