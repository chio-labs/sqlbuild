from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.planner.helpers.buildability import check_buildability
from sqlbuild.compiler.planner.models import MissingUpstream, WarehouseSnapshot
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    CheckBuildabilityTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_snapshot_from_relation_names,
    model_key,
    seed_key,
    source_key,
)

CHECK_BUILDABILITY_TEST_CASES: list[CheckBuildabilityTestCase] = [
    CheckBuildabilityTestCase(
        description="returns no missing when all deps are in scope",
        selected_keys=frozenset({model_key("a"), model_key("b")}),
        upstream_deps={
            model_key("a"): (),
            model_key("b"): (model_key("a"),),
        },
        existing_relation_names=(),
        expected_missing=(),
    ),
    CheckBuildabilityTestCase(
        description="returns no missing when dep exists in warehouse",
        selected_keys=frozenset({model_key("b")}),
        upstream_deps={
            model_key("b"): (model_key("a"),),
        },
        existing_relation_names=("a",),
        expected_missing=(),
    ),
    CheckBuildabilityTestCase(
        description="returns missing dep not in scope or warehouse",
        selected_keys=frozenset({model_key("b")}),
        upstream_deps={
            model_key("b"): (model_key("a"),),
        },
        existing_relation_names=(),
        expected_missing=(
            MissingUpstream(
                key=model_key("a"),
                required_by=(model_key("b"),),
            ),
        ),
    ),
    CheckBuildabilityTestCase(
        description="sorts missing by dependent count descending",
        selected_keys=frozenset({model_key("x"), model_key("y"), model_key("z")}),
        upstream_deps={
            model_key("x"): (model_key("a"), model_key("b")),
            model_key("y"): (model_key("a"),),
            model_key("z"): (model_key("b"),),
        },
        existing_relation_names=(),
        expected_missing=(
            MissingUpstream(
                key=model_key("a"),
                required_by=(model_key("x"), model_key("y")),
            ),
            MissingUpstream(
                key=model_key("b"),
                required_by=(model_key("x"), model_key("z")),
            ),
        ),
    ),
    CheckBuildabilityTestCase(
        description="source dep satisfied by warehouse relation",
        selected_keys=frozenset({model_key("orders")}),
        upstream_deps={
            model_key("orders"): (source_key("raw_orders"),),
        },
        existing_relation_names=("raw_orders",),
        expected_missing=(),
    ),
    CheckBuildabilityTestCase(
        description="seed dep in scope is not missing",
        selected_keys=frozenset({model_key("report"), seed_key("countries")}),
        upstream_deps={
            model_key("report"): (seed_key("countries"),),
            seed_key("countries"): (),
        },
        existing_relation_names=(),
        expected_missing=(),
    ),
    CheckBuildabilityTestCase(
        description="returns no missing for empty scope",
        selected_keys=frozenset(),
        upstream_deps={
            model_key("a"): (model_key("b"),),
        },
        existing_relation_names=(),
        expected_missing=(),
    ),
    CheckBuildabilityTestCase(
        description="deferred relation satisfies missing upstream",
        selected_keys=frozenset({model_key("b")}),
        upstream_deps={
            model_key("b"): (model_key("a"),),
        },
        existing_relation_names=(),
        deferred_relation_names=("a",),
        expected_missing=(),
    ),
    CheckBuildabilityTestCase(
        description="deferred relation does not satisfy unrelated upstream",
        selected_keys=frozenset({model_key("b")}),
        upstream_deps={
            model_key("b"): (model_key("a"),),
        },
        existing_relation_names=(),
        deferred_relation_names=("c",),
        expected_missing=(
            MissingUpstream(
                key=model_key("a"),
                required_by=(model_key("b"),),
            ),
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    CHECK_BUILDABILITY_TEST_CASES,
    ids=[case.description for case in CHECK_BUILDABILITY_TEST_CASES],
)
def test_given_scope_and_snapshot_when_checking_buildability_then_returns_expected(
    test_case: CheckBuildabilityTestCase,
) -> None:
    snapshot: WarehouseSnapshot = build_snapshot_from_relation_names(
        test_case.existing_relation_names
    )
    deferred_relations: dict[str, RelationInfo] = {
        name: RelationInfo(database=None, schema="prod", name=name, relation_type="BASE TABLE")
        for name in test_case.deferred_relation_names
    }

    result: tuple[MissingUpstream, ...] = check_buildability(
        selected_keys=test_case.selected_keys,
        upstream_deps=test_case.upstream_deps,
        snapshot=snapshot,
        deferred_relations=deferred_relations or None,
    )

    assert result == test_case.expected_missing
