from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.models import PlannerScope
from sqlbuild.compiler.source_freshness.main.propagation import (
    build_standard_source_freshness_propagation_result,
)
from sqlbuild.compiler.source_freshness.models import (
    StandardSourceFreshnessPlanningResult,
    StandardSourceFreshnessPropagationResult,
)
from sqlbuild.compiler.source_freshness.types import SourceFreshnessAgeStatus
from tests.unit.src.sqlbuild.compiler.source_freshness.main._test_types import (
    StandardSourceFreshnessPropagationTestCase,
)
from tests.unit.src.sqlbuild.compiler.source_freshness.main.helpers import (
    downstream_deps_from_edges,
    source_freshness_identity,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StandardSourceFreshnessPropagationTestCase(
            description="propagates changed source to direct downstream model",
            changed_source_names=("raw.orders",),
            unknown_source_names=(),
            downstream_edges={"source:raw.orders": ("model:orders",)},
            expected_stale_model_names=frozenset({"orders"}),
            expected_changed_source_model_names={"raw.orders": frozenset({"orders"})},
            expected_unknown_source_model_names={},
        ),
        StandardSourceFreshnessPropagationTestCase(
            description="propagates changed source through view to downstream table",
            changed_source_names=("raw.orders",),
            unknown_source_names=(),
            downstream_edges={
                "source:raw.orders": ("model:stg_orders",),
                "model:stg_orders": ("model:fact_orders",),
            },
            expected_stale_model_names=frozenset({"stg_orders", "fact_orders"}),
            expected_changed_source_model_names={
                "raw.orders": frozenset({"stg_orders", "fact_orders"})
            },
            expected_unknown_source_model_names={},
        ),
        StandardSourceFreshnessPropagationTestCase(
            description="preserves shared downstream for multiple changed sources",
            changed_source_names=("raw.orders", "raw.payments"),
            unknown_source_names=(),
            downstream_edges={
                "source:raw.orders": ("model:fact_orders",),
                "source:raw.payments": ("model:fact_orders",),
            },
            expected_stale_model_names=frozenset({"fact_orders"}),
            expected_changed_source_model_names={
                "raw.orders": frozenset({"fact_orders"}),
                "raw.payments": frozenset({"fact_orders"}),
            },
            expected_unknown_source_model_names={},
        ),
        StandardSourceFreshnessPropagationTestCase(
            description="propagates unknown source conservatively to downstream models",
            changed_source_names=(),
            unknown_source_names=("raw.orders",),
            downstream_edges={"source:raw.orders": ("model:orders",)},
            expected_stale_model_names=frozenset({"orders"}),
            expected_changed_source_model_names={},
            expected_unknown_source_model_names={"raw.orders": frozenset({"orders"})},
        ),
        StandardSourceFreshnessPropagationTestCase(
            description="propagates source age errors to blocked downstream models",
            changed_source_names=(),
            unknown_source_names=(),
            error_source_names=("raw.orders",),
            downstream_edges={
                "source:raw.orders": ("model:stg_orders",),
                "model:stg_orders": ("model:fact_orders",),
            },
            expected_stale_model_names=frozenset(),
            expected_blocked_model_names=frozenset({"stg_orders", "fact_orders"}),
            expected_changed_source_model_names={},
            expected_unknown_source_model_names={},
            expected_error_source_model_names={
                "raw.orders": frozenset({"stg_orders", "fact_orders"})
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_source_freshness_roots_when_propagating_then_returns_downstream_models(
    test_case: StandardSourceFreshnessPropagationTestCase,
) -> None:
    propagation: StandardSourceFreshnessPropagationResult = (
        build_standard_source_freshness_propagation_result(
            source_freshness=StandardSourceFreshnessPlanningResult(
                changed_identities=frozenset(
                    source_freshness_identity(source_name)
                    for source_name in test_case.changed_source_names
                ),
                unknown_source_names=test_case.unknown_source_names,
                age_statuses={
                    source_freshness_identity(source_name): SourceFreshnessAgeStatus.ERROR
                    for source_name in test_case.error_source_names
                },
            ),
            scope=PlannerScope(
                upstream_deps={},
                downstream_deps=downstream_deps_from_edges(test_case.downstream_edges),
                all_keys={},
                models_by_name={},
                selected_keys=frozenset(),
                execution_order=(),
            ),
        )
    )

    assert propagation.stale_model_names == test_case.expected_stale_model_names
    assert propagation.blocked_model_names == test_case.expected_blocked_model_names
    source_name: str
    expected_model_names: frozenset[str]
    for source_name, expected_model_names in test_case.expected_changed_source_model_names.items():
        assert (
            propagation.changed_source_model_names[source_freshness_identity(source_name)]
            == expected_model_names
        )
    for source_name, expected_model_names in test_case.expected_unknown_source_model_names.items():
        assert propagation.unknown_source_model_names[source_name] == expected_model_names
    for source_name, expected_model_names in (
        test_case.expected_error_source_model_names or {}
    ).items():
        assert (
            propagation.error_source_model_names[source_freshness_identity(source_name)]
            == expected_model_names
        )
