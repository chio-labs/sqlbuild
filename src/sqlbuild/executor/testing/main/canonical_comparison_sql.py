"""Public entrypoint for canonical SQL-test comparison formatting."""

from sqlbuild.executor.testing._helpers.comparison_sql import format_sql as _format_sql


def canonicalize_comparison_sql(
    *, sql: str, sql_analysis_dialect: str | None, sql_analysis_enabled: bool
) -> str:
    """Format generated SQL-test comparison SQL under the configured dialect."""

    return _format_sql(
        sql=sql,
        sql_analysis_dialect=sql_analysis_dialect,
        sql_analysis_enabled=sql_analysis_enabled,
    )
