"""Adapter-specific SQL-test analysis output corrections."""

from sqlbuild.compiler.planner._helpers.sql_tests.comments import (
    restore_sql_test_dialect_function_names as _restore_sql_test_dialect_function_names,
)


def restore_sql_test_dialect_function_names(*, sql: str, dialect: str | None) -> str:
    """Restore warehouse-supported function spellings after SQL analysis."""

    return _restore_sql_test_dialect_function_names(sql=sql, dialect=dialect)
