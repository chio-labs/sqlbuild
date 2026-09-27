"""Run-time warnings for project relation names hard-coded in Python SQL."""

from __future__ import annotations

import pytest

from sqlbuild.executor.python_nodes.classes.runtime_relation_guard import RuntimeRelationGuard
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.refs import model, source
from tests.unit.src.sqlbuild.executor.python_nodes.classes._test_types import (
    RuntimeRelationGuardTestCase,
)

_PROJECT_RELATIONS: dict[SqlResourceRef, str] = {
    model("customers"): "main.customers",
    model("orders"): "main.orders",
    source("raw_payments"): "raw.payments",
}


@pytest.mark.parametrize(
    "test_case",
    (
        RuntimeRelationGuardTestCase(
            description="unqualified model name resolved against the current schema warns once",
            statements=("SELECT * FROM customers", "SELECT count(*) FROM main.customers"),
            expected_warning_fragments=(
                "[P008] task 'export_orders' named model:customers as 'customers'",
            ),
        ),
        RuntimeRelationGuardTestCase(
            description="qualified source table warns",
            statements=("DELETE FROM raw.payments WHERE 1 = 0",),
            expected_warning_fragments=("named source:raw_payments as 'raw.payments'",),
        ),
        RuntimeRelationGuardTestCase(
            description="relation resolved through ctx.relation does not warn",
            statements=("SELECT * FROM main.customers",),
            expected_warning_fragments=(),
            resolved_refs=(model("customers"),),
        ),
        RuntimeRelationGuardTestCase(
            description="own destination does not warn",
            statements=("INSERT INTO orders SELECT 1",),
            expected_warning_fragments=(),
            own_refs=frozenset({model("orders")}),
        ),
        RuntimeRelationGuardTestCase(
            description="temporary tables and non-project relations do not warn",
            statements=(
                "CREATE TEMP TABLE customers AS SELECT 1 AS id",
                "SELECT * FROM customers JOIN information_schema.tables ON 1 = 0",
            ),
            expected_warning_fragments=(),
        ),
        RuntimeRelationGuardTestCase(
            description="unparseable SQL is not blocked and does not warn",
            statements=("VACUUM ((( customers",),
            expected_warning_fragments=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_python_sql_when_checking_then_warns_for_hard_coded_project_relations(
    test_case: RuntimeRelationGuardTestCase,
) -> None:
    warnings: list[str] = []
    guard: RuntimeRelationGuard = RuntimeRelationGuard(
        owner_label="task 'export_orders'",
        declare_help="declare it with depends_on={typed}",
        project_relations=_PROJECT_RELATIONS,
        dialect="duckdb",
        default_database=None,
        default_schema="main",
        warnings=warnings,
        own_refs=test_case.own_refs,
    )
    for ref in test_case.resolved_refs:
        guard.record_resolved(ref)

    for statement in test_case.statements:
        guard.check(statement)

    assert len(warnings) == len(test_case.expected_warning_fragments)
    assert all(
        fragment in warning
        for warning, fragment in zip(warnings, test_case.expected_warning_fragments, strict=True)
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
