"""Minimal projects that fail on declaration scopes: the index, visibility and relationships."""

from scripts.compiler_differential.constants import (
    FAILURE_BASE_FILES,
    FAILURE_MART_PATH,
    FAILURE_STAGING_PATH,
)
from scripts.compiler_differential.models import FailureCase

_STAGING_MACRO_PATH: str = "models/staging/_macros/amounts.py"
_STAGING_MACRO: str = "def staged_amount(value):\n    return f'{value} * 1'\n"
_STAGING_ENUM_PATH: str = "models/staging/_enums/status.sql"
_STAGING_ENUM: str = "ENUM (name staged_status, members [PLACED]);\n"
_MART_HEADER: str = 'MODEL (\n  description "Order totals per customer",\n);\n\n'
_STAGING_HEADER: str = 'MODEL (\n  description "Staged orders",\n);\n\n'
_TEST_PATH: str = "tests/unit/test_customer_totals.sql"


def _case(*, name: str, expected_code: str, files: dict[str, str]) -> FailureCase:
    return FailureCase(
        files={**FAILURE_BASE_FILES, **files}, name=name, expected_code=expected_code
    )


def scope_failure_cases() -> tuple[FailureCase, ...]:
    """Return the declaration-scope failure cases in a stable order."""

    return (
        _case(
            name="scope-duplicate-scoped-enum",
            expected_code="P001",
            files={
                _STAGING_ENUM_PATH: _STAGING_ENUM,
                "enums/status.sql": "ENUM (name staged_status, members [SHIPPED]);\n",
            },
        ),
        _case(
            name="scope-inaccessible-local-macro",
            expected_code="P001",
            files={
                _STAGING_MACRO_PATH: _STAGING_MACRO,
                FAILURE_MART_PATH: _MART_HEADER
                + "SELECT customer_id, SUM(@staged_amount('amount')) AS total_amount\n"
                'FROM __ref("stg_orders")\nGROUP BY customer_id\n',
            },
        ),
        _case(
            name="scope-first-of-two-visibility-errors",
            expected_code="P001",
            files={
                _STAGING_ENUM_PATH: _STAGING_ENUM,
                "models/marts/_macros/totals.py": "def mart_total(value):\n    return value\n",
                FAILURE_STAGING_PATH: _STAGING_HEADER
                + "SELECT order_id, customer_id, @mart_total('amount') AS amount, status\n"
                'FROM __source("raw_orders")\n',
                FAILURE_MART_PATH: _MART_HEADER
                + "SELECT customer_id, SUM(amount) AS total_amount\n"
                'FROM __ref("stg_orders")\n'
                'WHERE status = @enum("staged_status").PLACED\nGROUP BY customer_id\n',
            },
        ),
        _case(
            name="scope-test-outside-relationship-grant",
            expected_code="P001",
            files={
                _STAGING_ENUM_PATH: _STAGING_ENUM,
                _TEST_PATH: 'TEST (name "totals_by_customer");\n\nWITH\n'
                "__ref__stg_orders AS (\n  SELECT 10 AS customer_id, 5 AS amount\n),\n"
                "__expected__customer_totals AS (\n"
                '  SELECT 10 AS customer_id, @enum("staged_status").PLACED AS status\n)\n'
                "SELECT 1\n",
            },
        ),
        _case(
            name="scope-malformed-expected-relationship",
            expected_code="P001",
            files={
                _STAGING_ENUM_PATH: _STAGING_ENUM,
                _TEST_PATH: 'TEST (name "totals_by_customer");\n\nWITH\n'
                "__ref__stg_orders AS (\n  SELECT 10 AS customer_id\n),\n"
                "__expected__ AS (\n  SELECT 10 AS customer_id\n)\nSELECT 1\n",
            },
        ),
    )
