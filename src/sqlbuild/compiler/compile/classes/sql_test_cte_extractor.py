"""SQL-test CTE extraction class."""

from __future__ import annotations

from sqlbuild._native import extract_sql_test_ctes
from sqlbuild.compiler.compile.models import CompileSqlTestCte
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


class SqlTestCteExtractor:
    """Expose authored SQL-test CTE parsing to compiler consumers."""

    @staticmethod
    def extract(
        *, sql: str, file_label: str, syntax: SqlLexicalSyntax
    ) -> tuple[CompileSqlTestCte, ...]:
        """Extract top-level SQL-test CTEs without classifying their roles."""

        return extract_sql_test_ctes(sql=sql, file_label=file_label, syntax=syntax)
