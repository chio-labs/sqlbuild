"""Tests for native-assisted logical SQL reference extraction."""

from __future__ import annotations

import pytest

from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    DialectSqlScanTestCase,
    SqlReferenceExtractionErrorTestCase,
    SqlReferenceExtractionTestCase,
)

_GENERIC_SQL_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax()


@pytest.mark.parametrize(
    "test_case",
    [
        SqlReferenceExtractionTestCase(
            description="simple references preserve authored order",
            sql=(
                "SELECT * FROM __source('orders') "
                'UNION ALL SELECT * FROM __dbt_ref("shop", "customers")'
            ),
            expected_references=(
                (SqlReferenceKind.SOURCE, "orders", None),
                (SqlReferenceKind.DBT_REF, "customers", "shop"),
            ),
        ),
        SqlReferenceExtractionTestCase(
            description="dollar-quoted text hides embedded references",
            sql=(
                'SELECT $$Customer\'s order -- __ref("ignored") $5$$ AS order_label, '
                "$note$ $$ __seed('ignored') $note$ AS order_note "
                'FROM __ref("orders")'
            ),
            expected_references=((SqlReferenceKind.REF, "orders", None),),
        ),
        SqlReferenceExtractionTestCase(
            description="general scanner hides references in dollar-quoted text",
            sql=(
                'SELECT $$Customer\'s order __ref("ignored")$$ AS order_label '
                'FROM __table_fn("expand_orders")(1)'
            ),
            expected_references=((SqlReferenceKind.TABLE_FUNCTION, "expand_orders", None),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_simple_references_when_extracting_then_returns_authored_order(
    test_case: SqlReferenceExtractionTestCase,
) -> None:
    references: tuple[CompileSqlReference, ...] = extract_sql_references(
        sql=test_case.sql, syntax=_GENERIC_SQL_SYNTAX
    )

    assert (
        tuple(
            (reference.ref_kind, reference.ref_name, reference.ref_package)
            for reference in references
        )
        == test_case.expected_references
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SqlReferenceExtractionErrorTestCase(
            description="unclosed reference parenthesis preserves diagnostic",
            sql='SELECT * FROM __ref("orders"',
            expected_error="unclosed parenthesis",
        ),
        SqlReferenceExtractionErrorTestCase(
            description="expression reference name preserves diagnostic",
            sql="SELECT * FROM __ref(concat('ord', 'ers'))",
            expected_error="name argument must be a quoted string or identifier",
        ),
        SqlReferenceExtractionErrorTestCase(
            description="unclosed block comment preserves diagnostic",
            sql='SELECT * FROM __ref("orders") /* unterminated',
            expected_error="unclosed block comment",
        ),
        SqlReferenceExtractionErrorTestCase(
            description="unclosed quoted string preserves diagnostic",
            sql='SELECT * FROM __ref("orders") WHERE note = \'unterminated',
            expected_error="unclosed quoted string",
        ),
        SqlReferenceExtractionErrorTestCase(
            description="unclosed dollar-quoted string preserves diagnostic",
            sql='SELECT * FROM __ref("orders") WHERE note = $$customer\'s',
            expected_error="unclosed quoted string",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_reference_sql_when_extracting_then_preserves_python_diagnostic(
    test_case: SqlReferenceExtractionErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error):
        extract_sql_references(sql=test_case.sql, syntax=_GENERIC_SQL_SYNTAX)


@pytest.mark.parametrize(
    "test_case",
    [
        DialectSqlScanTestCase(
            description="snowflake backslash-escaped quote before a reference",
            syntax=SnowflakeAdapter.sql_lexical_syntax,
            sql="SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"orders\")",
            expected_names=("orders",),
        ),
        DialectSqlScanTestCase(
            description="bigquery backslash-escaped quote before a reference",
            syntax=BigQueryAdapter.sql_lexical_syntax,
            sql="SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"orders\")",
            expected_names=("orders",),
        ),
        DialectSqlScanTestCase(
            description="databricks backslash-escaped quote before a reference",
            syntax=DatabricksAdapter.sql_lexical_syntax,
            sql="SELECT 'O\\'Brien' AS customer_name, * FROM __ref(\"orders\")",
            expected_names=("orders",),
        ),
        DialectSqlScanTestCase(
            description="duckdb escape string before a reference",
            syntax=DuckDbAdapter.sql_lexical_syntax,
            sql="SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"orders\")",
            expected_names=("orders",),
        ),
        DialectSqlScanTestCase(
            description="postgres escape string before a reference",
            syntax=PostgresAdapter.sql_lexical_syntax,
            sql="SELECT E'O\\'Brien' AS customer_name, * FROM __ref(\"orders\")",
            expected_names=("orders",),
        ),
        DialectSqlScanTestCase(
            description="duckdb plain string keeps a literal backslash",
            syntax=DuckDbAdapter.sql_lexical_syntax,
            sql="SELECT 'C:\\' AS folder, * FROM __ref(\"orders\")",
            expected_names=("orders",),
        ),
        DialectSqlScanTestCase(
            description="databricks raw string keeps a literal backslash",
            syntax=DatabricksAdapter.sql_lexical_syntax,
            sql="SELECT r'C:\\' AS folder, * FROM __ref(\"orders\")",
            expected_names=("orders",),
        ),
        DialectSqlScanTestCase(
            description="bigquery triple-quoted string hides a reference",
            syntax=BigQueryAdapter.sql_lexical_syntax,
            sql="SELECT '''it's __ref(\"ignored\")''' AS note FROM __ref(\"orders\")",
            expected_names=("orders",),
        ),
        DialectSqlScanTestCase(
            description="bigquery hash comment hides a reference",
            syntax=BigQueryAdapter.sql_lexical_syntax,
            sql='SELECT 1 # __ref("ignored")\nFROM __ref("orders")',
            expected_names=("orders",),
        ),
        DialectSqlScanTestCase(
            description="snowflake slash comment hides a reference",
            syntax=SnowflakeAdapter.sql_lexical_syntax,
            sql='SELECT 1 // __ref("ignored")\nFROM __ref("orders")',
            expected_names=("orders",),
        ),
        DialectSqlScanTestCase(
            description="duckdb nested block comment hides a reference",
            syntax=DuckDbAdapter.sql_lexical_syntax,
            sql='SELECT 1 /* outer /* inner */ __ref("ignored") */ FROM __ref("orders")',
            expected_names=("orders",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dialect_sql_when_extracting_references_then_follows_dialect_lexical_rules(
    test_case: DialectSqlScanTestCase,
) -> None:
    references: tuple[CompileSqlReference, ...] = extract_sql_references(
        sql=test_case.sql, syntax=test_case.syntax
    )

    assert tuple(reference.ref_name for reference in references) == test_case.expected_names


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
