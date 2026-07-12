from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.helpers.sql.model_files import (
    model_header_column_locations,
    model_output_column_locations,
    parse_model_sql,
)
from sqlbuild.shared.models import PythonHookEntry, SqlHookEntry
from sqlbuild.spec.models.schema import SourceLocation
from tests.unit.src.sqlbuild.compiler.discovery.helpers._test_types import (
    ModelHeaderColumnLocationTestCase,
    ModelOutputColumnLocationTestCase,
    ParseModelSqlErrorTestCase,
    ParseModelSqlHeaderTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ParseModelSqlHeaderTestCase(
            description="accepts an empty model header",
            contents="""
        MODEL ();

        SELECT 1 AS order_id
        """,
            expected_header_values={},
            expected_query="SELECT 1 AS order_id",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts nested map and list header values",
            contents="""
        MODEL (
          materialized incremental,
          unique_key [order_id],
          config (
            cluster_by [event_day],
            transient true,
          ),
          row_diff_tolerances (
            revenue bounded-30d,
            order_count full,
          ),
        );

        SELECT order_id, event_day FROM raw_orders
        """,
            expected_header_values={
                "materialized": "incremental",
                "unique_key": ["order_id"],
                "config": {
                    "cluster_by": ["event_day"],
                    "transient": True,
                },
                "row_diff_tolerances": {
                    "revenue": "bounded-30d",
                    "order_count": "full",
                },
            },
            expected_query="SELECT order_id, event_day FROM raw_orders",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts blank lines and indentation inside the header",
            contents="""

        MODEL (
            materialized table,

            tags [core],
            enabled true,
        );

        SELECT 1
        """,
            expected_header_values={
                "materialized": "table",
                "tags": ["core"],
                "enabled": True,
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts quoted and unquoted string scalars",
            contents="""
        MODEL (
          materialized table,
          schema analytics,
          database preserve,
          replay_on_change bounded-30d,
        );

        SELECT 1
        """,
            expected_header_values={
                "materialized": "table",
                "schema": "analytics",
                "database": "preserve",
                "replay_on_change": "bounded-30d",
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts quoted, unquoted, and mixed string lists",
            contents="""
        MODEL (
          tags [core, 'finance', "data platform", marts],
          unique_key [order_id, customer_id],
        );

        SELECT 1
        """,
            expected_header_values={
                "tags": ["core", "finance", "data platform", "marts"],
                "unique_key": ["order_id", "customer_id"],
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts double quoted strings and escapes",
            contents="""
        MODEL (
          schema "analytics mart",
          description "Bob said \\"hello\\"",
          post_hooks [sql("grant select on @@CTX:destination.qualified to role analytics")],
        );

        SELECT 1
        """,
            expected_header_values={
                "schema": "analytics mart",
                "description": 'Bob said "hello"',
                "post_hooks": [
                    SqlHookEntry(
                        statement="grant select on @@CTX:destination.qualified to role analytics"
                    )
                ],
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts template-like strings when quoted",
            contents="""
        MODEL (
          schema 'dev_${user}',
          database 'ci_${ENV:GITHUB_RUN_ID}_${CTX:schema}',
          alias fact_orders,
        );

        SELECT 1
        """,
            expected_header_values={
                "schema": "dev_${user}",
                "database": "ci_${ENV:GITHUB_RUN_ID}_${CTX:schema}",
                "alias": "fact_orders",
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts nested maps with mixed quoted and unquoted strings",
            contents="""
        MODEL (
          row_diff_tolerances (
            revenue bounded-30d,
            order_count full,
          ),
          config (
            cluster_by [event_day, 'region'],
            transient true,
          ),
        );

        SELECT 1
        """,
            expected_header_values={
                "row_diff_tolerances": {
                    "revenue": "bounded-30d",
                    "order_count": "full",
                },
                "config": {
                    "cluster_by": ["event_day", "region"],
                    "transient": True,
                },
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts booleans and integers from unquoted scalars",
            contents="""
        MODEL (
          enabled false,
          batch_concurrency 4,
          config (
            transient true,
          ),
        );

        SELECT 1
        """,
            expected_header_values={
                "enabled": False,
                "batch_concurrency": 4,
                "config": {
                    "transient": True,
                },
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts callable audit entries in header lists",
            contents="""
        MODEL (
          columns (
            status (
              audits [accepted_values (values ["placed", "completed"])],
            ),
          ),
        );

        SELECT 1
        """,
            expected_header_values={
                "columns": {
                    "status": {
                        "audits": [
                            {"accepted_values": {"values": ["placed", "completed"]}},
                        ],
                    },
                },
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts relation calls as audit argument values",
            contents="""
        MODEL (
          columns (
            customer_id (
              audits [relationships (to __ref("dim_customers"), field customer_id)],
            ),
          ),
        );

        SELECT 1
        """,
            expected_header_values={
                "columns": {
                    "customer_id": {
                        "audits": [
                            {
                                "relationships": {
                                    "to": '__ref("dim_customers")',
                                    "field": "customer_id",
                                }
                            },
                        ],
                    },
                },
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts typed SQL and Python lifecycle hooks",
            contents="""
        MODEL (
          pre_hooks [
            sql("insert into audit_log select 'starting'"),
            python("notify", channel: "#data", attempts: 2, urgent: true),
          ],
          post_hooks [
            python("notify success", message: "@@CTX:destination.qualified"),
            sql("grant select on @@CTX:destination.qualified to role analytics"),
          ],
        );

        SELECT 1
        """,
            expected_header_values={
                "pre_hooks": [
                    SqlHookEntry(statement="insert into audit_log select 'starting'"),
                    PythonHookEntry(
                        name="notify",
                        kwargs={"channel": "#data", "attempts": 2, "urgent": True},
                    ),
                ],
                "post_hooks": [
                    PythonHookEntry(
                        name="notify success",
                        kwargs={"message": "@@CTX:destination.qualified"},
                    ),
                    SqlHookEntry(
                        statement="grant select on @@CTX:destination.qualified to role analytics"
                    ),
                ],
            },
            expected_query="SELECT 1",
        ),
        ParseModelSqlHeaderTestCase(
            description="accepts python-only lifecycle hook list",
            contents="""
        MODEL (
          post_hooks [python("notify", channel: "alerts")]
        );

        SELECT 1
        """,
            expected_header_values={
                "post_hooks": [
                    PythonHookEntry(name="notify", kwargs={"channel": "alerts"}),
                ],
            },
            expected_query="SELECT 1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_model_header_variants_when_parsing_then_it_returns_expected_header_and_query(
    test_case: ParseModelSqlHeaderTestCase,
) -> None:
    header_values: dict[str, object]
    query: str
    header_values, query = parse_model_sql(
        contents=test_case.contents, file_path=Path("orders.sql")
    )

    assert header_values == test_case.expected_header_values
    assert query == test_case.expected_query


@pytest.mark.parametrize(
    "test_case",
    [
        ParseModelSqlErrorTestCase(
            description="raises when the model header is missing",
            contents="SELECT 1\n",
            expected_error_fragment="must start with a MODEL",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when the model body is empty",
            contents="MODEL ();\n",
            expected_error_fragment="must contain SQL after MODEL(...)",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when the model header does not start with a key",
            contents="""
        MODEL ([core, finance]);

        SELECT 1
        """,
            expected_error_fragment="expected key",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when the model header contains old colon syntax",
            contents="""
        MODEL (
          tags: [core, finance]
        );

        SELECT 1
        """,
            expected_error_fragment="use SQLBuild syntax 'tags value'",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when the model header contains an unterminated list",
            contents="""
        MODEL (
          tags [core, finance
        );

        SELECT 1
        """,
            expected_error_fragment="expected value",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when a double quoted string is unterminated",
            contents="""
        MODEL (
          schema "analytics
        );

        SELECT 1
        """,
            expected_error_fragment="unterminated double-quoted string",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when a quote appears inside a bare value",
            contents="""
        MODEL (
          schema analytics"mart
        );

        SELECT 1
        """,
            expected_error_fragment="quote the whole value",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when a value with spaces is not quoted",
            contents="""
        MODEL (
          schema analytics mart
        );

        SELECT 1
        """,
            expected_error_fragment="quote values with spaces",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when sql hook receives extra arguments",
            contents="""
        MODEL (
          pre_hooks [sql("select 1", label: "extra")]
        );

        SELECT 1
        """,
            expected_error_fragment="does not accept additional arguments",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when python hook name is not quoted",
            contents="""
        MODEL (
          post_hooks [python(notify)]
        );

        SELECT 1
        """,
            expected_error_fragment="requires a quoted hook name",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when python hook kwarg does not use colon syntax",
            contents="""
        MODEL (
          post_hooks [python("notify", channel "#data")]
        );

        SELECT 1
        """,
            expected_error_fragment="expected ':'",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when hook list uses unknown constructor",
            contents="""
        MODEL (
          post_hooks [notify("done")]
        );

        SELECT 1
        """,
            expected_error_fragment="post_hooks entries must use typed sql",
        ),
        ParseModelSqlErrorTestCase(
            description="raises when hook list uses uppercase constructor",
            contents="""
        MODEL (
          pre_hooks [SQL("SELECT 1")]
        );

        SELECT 1
        """,
            expected_error_fragment="pre_hooks entries must use typed sql",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_model_contents_when_parsing_then_it_raises_clear_errors(
    test_case: ParseModelSqlErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        parse_model_sql(contents=test_case.contents, file_path=Path("orders.sql"))


@pytest.mark.parametrize(
    "test_case",
    (
        ModelHeaderColumnLocationTestCase(
            description="locates top level model column declarations",
            contents=(
                "MODEL (\n"
                "  materialized view,\n"
                "  columns (\n"
                "    order_id (),\n"
                "    customer_id (type INTEGER),\n"
                "  ),\n"
                ");\n\n"
                "SELECT order_id FROM raw_orders\n"
            ),
            expected_locations={
                "order_id": (Path("models/orders.sql"), 4, 5, 4, 13),
                "customer_id": (Path("models/orders.sql"), 5, 5, 5, 16),
            },
        ),
        ModelHeaderColumnLocationTestCase(
            description="ignores nested metadata keys inside column declarations",
            contents=(
                "MODEL (\n"
                "  columns (\n"
                "    status (\n"
                '      description "Order status",\n'
                "      audits [accepted_values (values [placed, completed])],\n"
                "    ),\n"
                "  ),\n"
                ");\n\n"
                "SELECT status FROM raw_orders\n"
            ),
            expected_locations={
                "status": (Path("models/orders.sql"), 3, 5, 3, 11),
            },
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_model_header_columns_when_locating_then_returns_expected_locations(
    test_case: ModelHeaderColumnLocationTestCase,
) -> None:
    locations: dict[str, SourceLocation] = model_header_column_locations(
        contents=test_case.contents,
        relative_path=Path("models/orders.sql"),
    )

    assert {
        name: (
            location.path,
            location.line,
            location.column,
            location.end_line,
            location.end_column,
        )
        for name, location in locations.items()
    } == test_case.expected_locations


@pytest.mark.parametrize(
    "test_case",
    (
        ModelOutputColumnLocationTestCase(
            description="locates direct and aliased top level select outputs",
            contents=(
                "MODEL ();\n\n"
                "SELECT\n"
                "  o.order_id,\n"
                "  CAST(o.amount AS VARCHAR) AS amount_text\n"
                "FROM raw_orders o\n"
            ),
            expected_locations={
                "order_id": (Path("models/orders.sql"), 4, 3, 4, 13),
                "amount_text": (Path("models/orders.sql"), 5, 3, 5, 43),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="keeps commas inside expressions within one output span",
            contents=(
                "MODEL ();\n\n"
                "SELECT\n"
                "  COALESCE(first_name, last_name, 'unknown') AS display_name,\n"
                "  customer_id\n"
                "FROM raw_customers\n"
            ),
            expected_locations={
                "display_name": (Path("models/orders.sql"), 4, 3, 4, 61),
                "customer_id": (Path("models/orders.sql"), 5, 3, 5, 14),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="locates outer select outputs after ctes",
            contents=(
                "MODEL ();\n\n"
                "WITH prepared AS (\n"
                "  SELECT order_id, amount_cents FROM raw_orders\n"
                ")\n"
                "SELECT\n"
                "  order_id,\n"
                "  amount_cents AS total_cents\n"
                "FROM prepared\n"
            ),
            expected_locations={
                "order_id": (Path("models/orders.sql"), 7, 3, 7, 11),
                "total_cents": (Path("models/orders.sql"), 8, 3, 8, 30),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="locates quoted output aliases",
            contents=('MODEL ();\n\nSELECT\n  amount_cents AS "amount cents"\nFROM raw_orders\n'),
            expected_locations={
                "amount cents": (Path("models/orders.sql"), 4, 3, 4, 33),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="locates expressions containing nested select text inside parentheses",
            contents=(
                "MODEL ();\n\n"
                "SELECT\n"
                "  (SELECT MAX(amount_cents) FROM raw_payments) AS max_payment_cents\n"
                "FROM raw_orders\n"
            ),
            expected_locations={
                "max_payment_cents": (Path("models/orders.sql"), 4, 3, 4, 68),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="skips wildcard outputs",
            contents="MODEL ();\n\nSELECT * FROM raw_orders\n",
            expected_locations={},
        ),
        ModelOutputColumnLocationTestCase(
            description="locates alias without AS using sql_analysis projection identity",
            contents=(
                "MODEL ();\n\nSELECT\n  CAST(amount AS VARCHAR) amount_text\nFROM raw_orders\n"
            ),
            expected_locations={
                "amount_text": (Path("models/orders.sql"), 4, 3, 4, 38),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="locates select without from using sql_analysis projection identity",
            contents="MODEL ();\n\nSELECT 1 AS one\n",
            expected_locations={
                "one": (Path("models/orders.sql"), 3, 8, 3, 16),
            },
        ),
        ModelOutputColumnLocationTestCase(
            description="skips sql_analysis-only aliases when sql_analysis is disabled",
            contents=(
                "MODEL ();\n\nSELECT\n  CAST(amount AS VARCHAR) amount_text\nFROM raw_orders\n"
            ),
            expected_locations={},
            extract_implicit_alias_columns=False,
        ),
        ModelOutputColumnLocationTestCase(
            description="skips union query after first branch because it is ambiguous",
            contents=("MODEL ();\n\nSELECT id FROM raw_a\nUNION ALL\nSELECT id FROM raw_b\n"),
            expected_locations={},
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_model_select_outputs_when_locating_then_returns_expected_locations(
    test_case: ModelOutputColumnLocationTestCase,
) -> None:
    locations: dict[str, SourceLocation] = model_output_column_locations(
        contents=test_case.contents,
        relative_path=Path("models/orders.sql"),
        extract_implicit_alias_columns=test_case.extract_implicit_alias_columns,
    )

    assert {
        name: (
            location.path,
            location.line,
            location.column,
            location.end_line,
            location.end_column,
        )
        for name, location in locations.items()
    } == test_case.expected_locations
