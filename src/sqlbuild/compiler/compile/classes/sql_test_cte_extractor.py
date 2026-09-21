"""SQL-test CTE extraction class."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.sql_tests.core import (
    extract_unclassified_sql_test_ctes,
)
from sqlbuild.compiler.compile.models import CompileSqlTestCte


class SqlTestCteExtractor:
    """Expose authored SQL-test CTE parsing to compiler consumers."""

    @staticmethod
    def extract(*, sql: str, file_label: str) -> tuple[CompileSqlTestCte, ...]:
        """Extract top-level SQL-test CTEs without classifying their roles."""

        return extract_unclassified_sql_test_ctes(sql=sql, file_label=file_label)
