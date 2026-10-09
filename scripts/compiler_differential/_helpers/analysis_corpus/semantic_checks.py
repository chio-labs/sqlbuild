"""Failure cases owned by the native semantic completion lane."""

from scripts.compiler_differential._helpers.corpus.case_builder import (
    config_files,
    failure_case,
    mart_body_files,
    staging_files,
)
from scripts.compiler_differential.constants import FAILURE_BASE_STAGING, FAILURE_MART_PATH
from scripts.compiler_differential.models import FailureCase

_ORDERS: str = '__ref("stg_orders")'
_TIMED_STAGING: str = FAILURE_BASE_STAGING.replace(
    "amount, status", "amount, status, CAST('2026-01-01' AS TIMESTAMP) AS ordered_at"
)


def semantic_checks_failure_cases() -> tuple[FailureCase, ...]:
    """Return this lane's failure cases; the lane appends here without editing shared lists."""

    return (
        failure_case(
            name="semantic-recovered-downstream-uses",
            expected_code="B002",
            expected_message="Unknown column 'amonut' in raw_orders",
            expected_help="did you mean 'amount'?",
            expected_notes=(
                "raw_orders has: amount, status, customer_id, order_id",
                "1 downstream uses of stg_orders.amount were not checked because of this error",
            ),
            files={
                **staging_files(FAILURE_BASE_STAGING.replace("amount, status", "amonut, status")),
                **mart_body_files(
                    f"SELECT customer_id, SUM(amount) AS total_amount\nFROM {_ORDERS}\n"
                    "GROUP BY customer_id\n"
                ),
            },
        ),
        failure_case(
            name="semantic-qualified-alias-unknown-column",
            expected_code="B002",
            expected_message="Unknown column 'amonut' in stg_orders (as o)",
            expected_help="did you mean 'amount'?",
            files=mart_body_files(
                f"SELECT o.customer_id, SUM(o.amonut) AS total_amount\nFROM {_ORDERS} AS o\n"
                "GROUP BY o.customer_id\n"
            ),
        ),
        failure_case(
            name="semantic-temporal-comparison-help",
            expected_code="B217",
            expected_help="compare with a timestamp, for example TIMESTAMP '2026-04-01'",
            expected_notes=("o.ordered_at is TIMESTAMP, 5 is INTEGER",),
            expected_location=(7, 7),
            files={
                **staging_files(_TIMED_STAGING),
                **mart_body_files(
                    f"SELECT o.customer_id, SUM(o.amount) AS total_amount\nFROM {_ORDERS} AS o\n"
                    "WHERE o.ordered_at > 5\nGROUP BY o.customer_id\n"
                ),
            },
        ),
        failure_case(
            name="semantic-type-error-unchecked-uses",
            expected_code="B212",
            expected_notes=(
                "1 downstream output uses were not type-checked because of this error",
                "status is TEXT, 1 is INTEGER",
            ),
            files={
                **staging_files(
                    FAILURE_BASE_STAGING.replace("amount, status", "status + 1 AS amount, status")
                ),
                **mart_body_files(
                    f"SELECT customer_id, SUM(amount) AS total_amount\nFROM {_ORDERS}\n"
                    "GROUP BY customer_id\n"
                ),
            },
        ),
        failure_case(
            name="semantic-rejected-opt-out-counts-findings",
            expected_code="P009",
            expected_message="`sql_analysis false` is not needed for model 'customer_totals'",
            expected_help="hiding: 2 unknown columns, 1 type mismatch (run `sqb compile`",
            files={
                **config_files("\n[settings]\nrequire_sql_analysis = true\n"),
                FAILURE_MART_PATH: (
                    'MODEL (\n  description "Order totals per customer",\n'
                    "  sql_analysis false,\n);\n\n"
                    "SELECT customer_id, SUM(refund) AS total_amount, MAX(amonut) AS top_amount\n"
                    f"FROM {_ORDERS}\nWHERE status > 5\nGROUP BY customer_id\n"
                ),
            },
        ),
    )
