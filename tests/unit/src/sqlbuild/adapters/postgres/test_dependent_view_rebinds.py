"""Unit coverage for re-pointing PostgreSQL views bound to a promoted table."""

from __future__ import annotations

import pytest

from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from tests.unit.src.sqlbuild.adapters.postgres._test_types import (
    PostgresDependentViewRebindTestCase,
)
from tests.unit.src.sqlbuild.adapters.postgres.helpers import (
    FakePostgresConnection,
    FakePostgresCursor,
)

_DEFINITION: str = " SELECT orders.order_id\n   FROM dev.orders;"
_BODY: str = "SELECT orders.order_id\n   FROM dev.orders"


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresDependentViewRebindTestCase(
            description="view without options is re-created plainly",
            catalog_rows=(("reporting", "orders_dashboard", _DEFINITION, None),),
            expected_statements=(
                f'CREATE OR REPLACE VIEW "reporting"."orders_dashboard" AS {_BODY}',
            ),
        ),
        PostgresDependentViewRebindTestCase(
            description="security options are re-emitted in the with clause",
            catalog_rows=(
                (
                    "reporting",
                    "orders_secure",
                    _DEFINITION,
                    "security_barrier=true\x1fsecurity_invoker=true",
                ),
            ),
            expected_statements=(
                'CREATE OR REPLACE VIEW "reporting"."orders_secure" '
                f"WITH (security_barrier=true, security_invoker=true) AS {_BODY}",
            ),
        ),
        PostgresDependentViewRebindTestCase(
            description="check option is re-emitted after the query",
            catalog_rows=(
                (
                    "reporting",
                    "orders_checked",
                    _DEFINITION,
                    "check_option=cascaded\x1fsecurity_barrier=false",
                ),
            ),
            expected_statements=(
                'CREATE OR REPLACE VIEW "reporting"."orders_checked" '
                f"WITH (security_barrier=false) AS {_BODY} WITH CASCADED CHECK OPTION",
            ),
        ),
        PostgresDependentViewRebindTestCase(
            description="local check option alone adds no with clause",
            catalog_rows=(("reporting", "orders_local", _DEFINITION, "check_option=local"),),
            expected_statements=(
                'CREATE OR REPLACE VIEW "reporting"."orders_local" '
                f"AS {_BODY} WITH LOCAL CHECK OPTION",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dependent_views_when_capturing_rebinds_then_view_options_survive(
    test_case: PostgresDependentViewRebindTestCase,
) -> None:
    """CREATE OR REPLACE VIEW resets omitted options, so every captured option is re-emitted."""

    connection: FakePostgresConnection = FakePostgresConnection(
        FakePostgresCursor(rows=test_case.catalog_rows)
    )

    statements: tuple[str, ...] = PostgresAdapter().capture_dependent_view_rebinds(
        connection=connection, database=None, schema="dev", name="orders"
    )

    assert statements == test_case.expected_statements
    assert "reloptions" in connection.executed_sql[0]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
