"""Tests for audit SQL rendering with relation overrides."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.auditing.main.render import render_audit_sql
from sqlbuild.compiler.compile.models.core import CompiledRelationTarget
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.compiler.auditing.main._test_types import (
    RenderAuditSqlTestCase,
)
from tests.unit.src.sqlbuild.compiler.auditing.main.helpers import (
    build_render_model_targets,
    build_render_seed_targets,
    build_render_source_map,
)

RENDER_TEST_CASES: list[RenderAuditSqlTestCase] = [
    RenderAuditSqlTestCase(
        description="resolves ref to qualified model name without overrides",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        model_targets={"orders": "staging.orders"},
        source_map_entries={},
        expected_sql_fragment="SELECT id FROM staging.orders WHERE id IS NULL",
    ),
    RenderAuditSqlTestCase(
        description="resolves source to qualified name",
        unresolved_sql='SELECT id FROM __source("raw_orders") WHERE id IS NULL',
        model_targets={},
        source_map_entries={"raw_orders": (None, "public", "orders")},
        expected_sql_fragment="SELECT id FROM public.orders WHERE id IS NULL",
    ),
    RenderAuditSqlTestCase(
        description="override replaces ref instead of normal target",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        model_targets={"orders": "staging.orders"},
        source_map_entries={},
        relation_overrides={"orders": "staging.orders__staging"},
        expected_sql_fragment="SELECT id FROM staging.orders__staging WHERE id IS NULL",
    ),
    RenderAuditSqlTestCase(
        description="override applies only to matching ref",
        unresolved_sql=(
            'SELECT a.id FROM __ref("orders") a JOIN __ref("customers") b ON a.cid = b.id'
        ),
        model_targets={"orders": "staging.orders", "customers": "staging.customers"},
        source_map_entries={},
        relation_overrides={"orders": "staging.orders__delta"},
        expected_sql_fragment=(
            "SELECT a.id FROM staging.orders__delta a JOIN staging.customers b ON a.cid = b.id"
        ),
    ),
    RenderAuditSqlTestCase(
        description="source refs unaffected by relation overrides",
        unresolved_sql=(
            'SELECT a.id FROM __ref("orders") a JOIN __source("raw_orders") b ON a.id = b.id'
        ),
        model_targets={"orders": "staging.orders"},
        source_map_entries={"raw_orders": (None, "public", "orders")},
        relation_overrides={"orders": "staging.orders__staging"},
        expected_sql_fragment=(
            "SELECT a.id FROM staging.orders__staging a JOIN public.orders b ON a.id = b.id"
        ),
    ),
    RenderAuditSqlTestCase(
        description="unknown ref left as-is when no override",
        unresolved_sql='SELECT id FROM __ref("missing") WHERE id IS NULL',
        model_targets={},
        source_map_entries={},
        expected_sql_fragment='__ref("missing")',
    ),
    RenderAuditSqlTestCase(
        description="seed target resolved when no override",
        unresolved_sql='SELECT code FROM __ref("country_codes")',
        model_targets={},
        source_map_entries={},
        seed_targets={"country_codes": "main.country_codes"},
        expected_sql_fragment="SELECT code FROM main.country_codes",
    ),
    RenderAuditSqlTestCase(
        description="seed call resolves to qualified seed name",
        unresolved_sql='SELECT code FROM __seed("country_codes")',
        model_targets={},
        source_map_entries={},
        seed_targets={"country_codes": "main.country_codes"},
        expected_sql_fragment="SELECT code FROM main.country_codes",
    ),
    RenderAuditSqlTestCase(
        description="override takes precedence over seed target",
        unresolved_sql='SELECT code FROM __ref("country_codes")',
        model_targets={},
        source_map_entries={},
        seed_targets={"country_codes": "main.country_codes"},
        relation_overrides={"country_codes": "tmp.country_codes__staging"},
        expected_sql_fragment="SELECT code FROM tmp.country_codes__staging",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RENDER_TEST_CASES,
    ids=[case.description for case in RENDER_TEST_CASES],
)
def test_given_unresolved_sql_when_rendering_then_returns_expected(
    test_case: RenderAuditSqlTestCase,
) -> None:
    model_targets: dict[str, CompiledRelationTarget] = build_render_model_targets(
        test_case.model_targets
    )
    seed_targets: dict[str, CompiledRelationTarget] = build_render_seed_targets(
        test_case.seed_targets
    )
    source_map: dict[str, SourceEntry] = build_render_source_map(test_case.source_map_entries)

    result: str = render_audit_sql(
        unresolved_sql=test_case.unresolved_sql,
        model_targets=model_targets,
        seed_targets=seed_targets,
        source_map=source_map,
        relation_overrides=test_case.relation_overrides if test_case.relation_overrides else None,
    )

    assert test_case.expected_sql_fragment in result
