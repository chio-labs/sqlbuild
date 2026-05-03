"""Tests for cursor upstream qualified name resolution with deferred targets."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledRelationTarget,
    CompileSqlReference,
)
from sqlbuild.compiler.planner.helpers.warehouse_snapshot import (
    _resolve_upstream_qualified_name,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    CursorUpstreamResolutionTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_cursor_deferred_targets,
    build_cursor_model_map,
    build_cursor_ref,
)

TEST_CASES: list[CursorUpstreamResolutionTestCase] = [
    CursorUpstreamResolutionTestCase(
        description="non-deferred ref resolves to model target",
        ref_name="orders",
        model_qualified_name="staging.orders",
        deferred_qualified_name=None,
        selected_names=None,
        expected_qualified_name="staging.orders",
    ),
    CursorUpstreamResolutionTestCase(
        description="deferred non-selected ref resolves to deferred target",
        ref_name="orders",
        model_qualified_name="dev.orders",
        deferred_qualified_name="prod.orders",
        selected_names=frozenset({"fact_orders"}),
        expected_qualified_name="prod.orders",
    ),
    CursorUpstreamResolutionTestCase(
        description="deferred selected ref resolves to current target not deferred",
        ref_name="orders",
        model_qualified_name="dev.orders",
        deferred_qualified_name="prod.orders",
        selected_names=frozenset({"orders", "fact_orders"}),
        expected_qualified_name="dev.orders",
    ),
    CursorUpstreamResolutionTestCase(
        description="deferred with no selected_names uses deferred target",
        ref_name="orders",
        model_qualified_name="dev.orders",
        deferred_qualified_name="prod.orders",
        selected_names=None,
        expected_qualified_name="prod.orders",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_ref_and_deferred_targets_when_resolving_upstream_then_returns_expected(
    test_case: CursorUpstreamResolutionTestCase,
) -> None:
    ref: CompileSqlReference = build_cursor_ref(test_case.ref_name)
    model_map: dict[str, CompiledModel] = build_cursor_model_map(
        test_case.ref_name,
        test_case.model_qualified_name,
    )
    deferred_targets: dict[str, CompiledRelationTarget] | None = build_cursor_deferred_targets(
        test_case.ref_name,
        test_case.deferred_qualified_name,
    )

    result: str | None = _resolve_upstream_qualified_name(
        ref=ref,
        model_map=model_map,
        source_map={},
        deferred_targets=deferred_targets,
        selected_names=test_case.selected_names,
    )

    assert result == test_case.expected_qualified_name
