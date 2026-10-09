"""Failure cases owned by the native model analysis session lane."""

from scripts.compiler_differential._helpers.corpus.case_builder import failure_case
from scripts.compiler_differential.constants import FAILURE_MART_PATH, FAILURE_STAGING_PATH
from scripts.compiler_differential.models import FailureCase

_ORDERS: str = '__ref("stg_orders")'
_MART_HEADER: str = 'MODEL (\n  description "Order totals per customer",\n);\n\n'
_STAGING_HEADER: str = 'MODEL (\n  description "Staged orders",\n);\n\n'
_LAYERED_PATH: str = "models/marts/order_layers.sql"
_LAYERED_MODEL: str = (
    'MODEL (\n  description "Orders layered over the staged star",\n);\n\n'
    f"SELECT s.*, s.amount * 2 AS doubled_amount\nFROM {_ORDERS} s\n"
)


def analysis_session_failure_cases() -> tuple[FailureCase, ...]:
    """Return this lane's failure cases; the lane appends here without editing shared lists."""

    return (
        failure_case(
            name="analysis-session-star-published-unknown-column",
            expected_code="B002",
            files={
                FAILURE_STAGING_PATH: _STAGING_HEADER + 'SELECT *\nFROM __source("raw_orders")\n',
                _LAYERED_PATH: _LAYERED_MODEL,
                FAILURE_MART_PATH: _MART_HEADER
                + "SELECT customer_id, SUM(missing_amount) AS total_amount\n"
                'FROM __ref("order_layers")\nGROUP BY customer_id\n',
            },
        ),
        failure_case(
            name="analysis-session-set-operation-unknown-column",
            expected_code="B002",
            files={
                FAILURE_MART_PATH: _MART_HEADER
                + f"SELECT customer_id, amount AS total_amount FROM {_ORDERS}\n"
                f"UNION ALL\nSELECT customer_id, refund_amount FROM {_ORDERS}\n",
            },
        ),
        failure_case(
            name="analysis-session-cte-chain-unknown-column",
            expected_code="B002",
            files={
                FAILURE_MART_PATH: _MART_HEADER + f"WITH base AS (SELECT * FROM {_ORDERS}),\n"
                "totals AS (SELECT customer_id, SUM(amount) AS total_amount FROM base GROUP BY 1)\n"
                "SELECT customer_id, total_amount, order_count FROM totals\n",
            },
        ),
    )
