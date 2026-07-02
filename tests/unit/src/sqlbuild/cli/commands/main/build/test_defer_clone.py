from __future__ import annotations

import pytest

from sqlbuild.cli.commands.helpers.build.defer_clone import defer_clone_boundary_selectors
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import PlannerScope
from tests.unit.src.sqlbuild.cli.commands.main.build._test_types import (
    DeferCloneBoundaryTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.build.helpers import (
    build_compiled_object_key,
)

MODEL_A: CompiledObjectKey = build_compiled_object_key(CompiledResourceType.MODEL, "a")
MODEL_B: CompiledObjectKey = build_compiled_object_key(CompiledResourceType.MODEL, "b")
MODEL_C: CompiledObjectKey = build_compiled_object_key(CompiledResourceType.MODEL, "c")
SEED_COUNTRIES: CompiledObjectKey = build_compiled_object_key(
    CompiledResourceType.SEED, "countries"
)
SOURCE_RAW: CompiledObjectKey = build_compiled_object_key(CompiledResourceType.SOURCE, "raw_orders")


TEST_CASES: list[DeferCloneBoundaryTestCase] = [
    DeferCloneBoundaryTestCase(
        description="clones the first non-view ancestor and stops",
        selected_keys=frozenset({MODEL_C}),
        upstream_deps={
            MODEL_C: (MODEL_B, SOURCE_RAW),
            MODEL_B: (MODEL_A, SEED_COUNTRIES),
            MODEL_A: (),
            SEED_COUNTRIES: (),
            SOURCE_RAW: (),
        },
        expected_selectors=("b",),
    ),
    DeferCloneBoundaryTestCase(
        description="excludes selected upstreams but includes their own boundary",
        selected_keys=frozenset({MODEL_B, MODEL_C}),
        upstream_deps={
            MODEL_C: (MODEL_B,),
            MODEL_B: (MODEL_A,),
            MODEL_A: (),
        },
        expected_selectors=("a",),
    ),
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_scope_when_resolving_defer_clone_boundary_then_returns_expected_selectors(
    test_case: DeferCloneBoundaryTestCase,
) -> None:
    scope: PlannerScope = PlannerScope(
        selected_keys=test_case.selected_keys,
        upstream_deps=test_case.upstream_deps,
        downstream_deps={},
        all_keys={},
        models_by_name={},
        execution_order=(),
    )

    result: tuple[str, ...] = defer_clone_boundary_selectors(scope=scope)

    assert result == test_case.expected_selectors
