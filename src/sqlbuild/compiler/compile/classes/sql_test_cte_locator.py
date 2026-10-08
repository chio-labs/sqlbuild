"""SQL-test CTE location class."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.sql_tests.helper_ctes import sql_test_cte_location
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

        return sql_test_cte_location(
            test_file=test_file, test_block=test_block, cte_name=cte_name, call=call
        )
