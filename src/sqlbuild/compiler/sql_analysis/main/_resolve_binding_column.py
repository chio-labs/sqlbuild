"""Resolve schema column spellings using dialect identifier semantics."""

from collections.abc import Mapping

from sqlbuild.compiler.sql_analysis.constants import (
    CASE_SENSITIVE_BINDING_DIALECTS,
    NATIVE_DIALECT_ALIASES,
    SNOWFLAKE_DIALECT_NAME,
    SQL_QUOTED_IDENTIFIER_DELIMITER,
)


def resolve_binding_column(
    *, name: str, columns: Mapping[str, str], dialect: str | None, ignore_quoted_case: bool = False
) -> str | None:
    dialect = NATIVE_DIALECT_ALIASES.get(dialect or "generic", dialect)

    def identity(value: str) -> str:
        quoted: bool = value.startswith(SQL_QUOTED_IDENTIFIER_DELIMITER) and value.endswith(
            SQL_QUOTED_IDENTIFIER_DELIMITER
        )
        raw: str = value[1:-1].replace('""', '"') if quoted else value
        if quoted and dialect in CASE_SENSITIVE_BINDING_DIALECTS and not ignore_quoted_case:
            return raw
        return raw.upper() if dialect == SNOWFLAKE_DIALECT_NAME else raw.casefold()

    expected: str = identity(name)
    return next((column for column in columns if identity(column) == expected), None)
