"""Minimal projects whose model SQL holds a malformed reference call."""

from scripts.compiler_differential._helpers.corpus.case_builder import (
    failure_case,
    mart_body_files,
    staging_files,
)
from scripts.compiler_differential.models import FailureCase

_SELECT: str = "SELECT order_id AS customer_id, 1 AS total_amount\n"
_STAGING_HEADER: str = 'MODEL (\n  description "Staged orders",\n);\n\n'
_HIDDEN_CALLS: str = (
    "-- __ref(hidden)\n"
    "SELECT order_id AS customer_id, 'é __ref(hidden)' AS note, $$__ref(hidden)$$ AS body,\n"
    "  1 AS total_amount /* __ref(hidden) */\n"
)


def _mart_from(
    *, name: str, from_clause: str, expected_code: str, expected_message: str
) -> FailureCase:
    return failure_case(
        name=name,
        expected_code=expected_code,
        expected_message=expected_message,
        files=mart_body_files(f"{_SELECT}FROM {from_clause}\n"),
    )


def reference_failure_cases() -> tuple[FailureCase, ...]:
    """Return the reference-extraction failure cases in a stable order."""

    return (
        _mart_from(
            name="reference-two-name-arguments",
            from_clause='__ref("stg_orders", "orders")',
            expected_code="P012",
            expected_message='__ref("stg_orders", "orders") is not a valid __ref() call',
        ),
        _mart_from(
            name="reference-dbt-three-arguments",
            from_clause='__dbt_ref("shop", "orders", "extra")',
            expected_code="P012",
            expected_message='__dbt_ref("shop", "orders", "extra") is not a valid __dbt_ref() call',
        ),
        _mart_from(
            name="reference-empty-argument",
            from_clause='__ref("stg_orders", )',
            expected_code="P012",
            expected_message='__ref("stg_orders", ) is not a valid __ref() call',
        ),
        _mart_from(
            name="reference-expression-name",
            from_clause="__ref(concat('stg_', 'orders'))",
            expected_code="P012",
            expected_message="__ref(concat('stg_', 'orders')) is not a valid __ref() call",
        ),
        _mart_from(
            name="reference-unclosed-call",
            from_clause='__ref("stg_orders"',
            expected_code="P001",
            expected_message="SQL reference contains an unclosed parenthesis",
        ),
        _mart_from(
            name="table-function-without-arguments",
            from_clause='__table_fn("table_fn__orders_for") /* no call */',
            expected_code="P012",
            expected_message="__table_fn must be followed by an argument list",
        ),
        _mart_from(
            name="table-function-single-quoted-name",
            from_clause="__table_fn('table_fn__orders_for')(1)",
            expected_code="P012",
            expected_message="__table_fn('table_fn__orders_for') is not a valid __table_fn() call",
        ),
        _mart_from(
            name="table-function-empty-call-argument",
            from_clause='__table_fn("table_fn__orders_for")(1, , 2)',
            expected_code="P001",
            expected_message="SQL reference contains an empty argument",
        ),
        _mart_from(
            name="table-function-unclosed-call",
            from_clause='__table_fn("table_fn__orders_for")(1 -- )',
            expected_code="P001",
            expected_message="SQL table function call contains an unclosed parenthesis",
        ),
        failure_case(
            name="reference-several-rejected-calls-in-one-file",
            expected_code="P012",
            expected_message="__ref(stg_orders) is not a valid __ref() call",
            expected_help=(
                "__ref() takes exactly one double-quoted name, with no comments or extra spaces "
                'inside the parentheses: __ref("stg_orders")'
            ),
            expected_location=(8, 6),
            expected_codes=("P012", "P012", "P012"),
            files=mart_body_files(
                f"{_HIDDEN_CALLS}FROM __ref(stg_orders)\n"
                "JOIN __source( 'raw_orders' ) USING (customer_id)\n"
                'WHERE customer_id IN (SELECT customer_id FROM __seed("a", "b"))\n'
            ),
        ),
        failure_case(
            name="reference-rejected-calls-across-files",
            expected_code="P012",
            expected_message="__dbt_ref(shop, orders, extra) is not a valid __dbt_ref() call",
            expected_codes=("P012", "P012"),
            files={
                **mart_body_files(f"{_SELECT}FROM __dbt_ref(shop, orders, extra)\n"),
                **staging_files(
                    f"{_STAGING_HEADER}SELECT order_id, customer_id, amount, status\n"
                    'FROM __table_fn("table_fn__orders_for") -- no call\n'
                ),
            },
        ),
        failure_case(
            name="reference-error-after-rejected-calls",
            expected_code="P001",
            expected_message="SQL reference contains an unclosed quoted string",
            files=mart_body_files(
                f"{_SELECT}FROM __ref(stg_orders)\nWHERE __ref(other) IS NULL AND note = 'open\n"
            ),
        ),
    )
