"""SQL-test CTE location class."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.models import DiscoveredSqlTestBlock, DiscoveredSqlTestFile
from sqlbuild.spec.contracts.models import SourceLocation


class SqlTestCteLocator:
    """Expose SQL-test CTE and reference-call locations to compiler consumers."""

    @staticmethod
    def locate(
        *,
        test_file: DiscoveredSqlTestFile,
        test_block: DiscoveredSqlTestBlock,
        cte_name: str,
        call: str | None,
    ) -> SourceLocation:
        """Locate a call inside one CTE of a SQL test block, else the CTE header, else the block."""

        line, column, end_line, end_column = _native.sql_test_cte_span(
            test_file.contents, test_block.sql_body, cte_name, call
        )
        return SourceLocation(
            path=test_file.relative_path,
            line=line,
            column=column,
            end_line=end_line,
            end_column=end_column,
        )
