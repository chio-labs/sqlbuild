from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import (
    CompiledAudit,
    CompiledRelationLocation,
)
from sqlbuild.compiler.planner.helpers.output.audit_entry import plan_audit
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.spec.contracts.models import SourceEntry
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    PlanAuditTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    PlannerTestAdapter,
    build_audit_from_test_case,
    build_audit_model_locations,
    build_audit_source_map,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PlanAuditTestCase(
            description="resolves ref to qualified model name",
            sql_body=('SELECT id FROM __ref("orders") WHERE id IS NULL'),
            model_locations={"orders": "staging.orders"},
            source_map_entries={},
            expected_sql_fragment=("SELECT id FROM staging.orders WHERE id IS NULL"),
        ),
        PlanAuditTestCase(
            description="resolves source to qualified name",
            sql_body=('SELECT id FROM __source("raw_orders") WHERE id IS NULL'),
            model_locations={},
            source_map_entries={
                "raw_orders": (None, "public", "orders"),
            },
            expected_sql_fragment=("SELECT id FROM public.orders WHERE id IS NULL"),
        ),
        PlanAuditTestCase(
            description="resolves both ref and source in same query",
            sql_body=(
                'SELECT a.id FROM __ref("orders") a JOIN __source("raw_orders") b ON a.id = b.id'
            ),
            model_locations={"orders": "staging.orders"},
            source_map_entries={
                "raw_orders": (None, "public", "orders"),
            },
            expected_sql_fragment=(
                "SELECT a.id FROM staging.orders a JOIN public.orders b ON a.id = b.id"
            ),
        ),
        PlanAuditTestCase(
            description=("source with database includes database in qualified name"),
            sql_body='SELECT id FROM __source("raw_orders")',
            model_locations={},
            source_map_entries={
                "raw_orders": ("raw_db", "public", "orders"),
            },
            expected_sql_fragment=("SELECT id FROM raw_db.public.orders"),
        ),
        PlanAuditTestCase(
            description="propagates always_run to audit plan entry",
            sql_body=('SELECT id FROM __ref("orders") WHERE id IS NULL'),
            model_locations={"orders": "staging.orders"},
            source_map_entries={},
            always_run=True,
            expected_sql_fragment=("SELECT id FROM staging.orders WHERE id IS NULL"),
            expected_always_run=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_audit_when_planning_then_resolves_sql(
    test_case: PlanAuditTestCase,
) -> None:
    audit: CompiledAudit = build_audit_from_test_case(test_case)
    model_locations: dict[str, CompiledRelationLocation] = build_audit_model_locations(
        test_case.model_locations
    )
    source_map: dict[str, SourceEntry] = build_audit_source_map(test_case.source_map_entries)

    result: AuditPlanEntry = plan_audit(
        audit=audit,
        model_locations=model_locations,
        seed_locations={},
        source_map=source_map,
        adapter=PlannerTestAdapter(),
        upstream_deps={},
        downstream_deps={},
        model_materializations={},
    )

    assert test_case.expected_sql_fragment in result.resolved_sql
    assert result.always_run is test_case.expected_always_run


@pytest.mark.parametrize(
    "test_case",
    [
        PlanAuditTestCase(
            description="unknown ref raises clear error",
            sql_body=('SELECT id FROM __ref("missing") WHERE id IS NULL'),
            model_locations={},
            source_map_entries={},
            expected_sql_fragment="",
            expected_error_fragment=r"still contains unresolved __ref\(\) markers",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_audit_with_unresolved_marker_when_planning_then_it_raises_clear_error(
    test_case: PlanAuditTestCase,
) -> None:
    audit: CompiledAudit = build_audit_from_test_case(test_case)
    model_locations: dict[str, CompiledRelationLocation] = build_audit_model_locations(
        test_case.model_locations
    )
    source_map: dict[str, SourceEntry] = build_audit_source_map(test_case.source_map_entries)

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        plan_audit(
            audit=audit,
            model_locations=model_locations,
            seed_locations={},
            source_map=source_map,
            adapter=PlannerTestAdapter(),
            upstream_deps={},
            downstream_deps={},
            model_materializations={},
        )
