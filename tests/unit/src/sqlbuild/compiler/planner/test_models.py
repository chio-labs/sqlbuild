from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import ModelPlanEntry, RelationReusePlan
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    PlanAction,
    PlanReason,
    RelationReuseKind,
)
from tests.unit.src.sqlbuild.compiler.planner._test_types import (
    RelationReuseValidationTestCase,
)

RELATION_REUSE_VALIDATION_TEST_CASES: list[RelationReuseValidationTestCase] = [
    RelationReuseValidationTestCase(
        description="complete relation reuse rejects incremental materialization",
        materialization_type=MaterializationType.INCREMENTAL,
        action=PlanAction.INCREMENTAL_APPEND,
        reuse_kind=RelationReuseKind.COMPLETE_RELATION_REUSE,
        expected_error_fragment="complete relation reuse requires table materialization",
    ),
    RelationReuseValidationTestCase(
        description="seeded relation reuse rejects table materialization",
        materialization_type=MaterializationType.TABLE,
        action=PlanAction.CREATE_TABLE,
        reuse_kind=RelationReuseKind.SEEDED_RELATION_REUSE,
        expected_error_fragment=(
            "seeded relation reuse requires incremental, snapshot, or custom materialization"
        ),
    ),
    RelationReuseValidationTestCase(
        description="seeded relation reuse rejects non incremental action",
        materialization_type=MaterializationType.INCREMENTAL,
        action=PlanAction.CREATE_TABLE,
        reuse_kind=RelationReuseKind.SEEDED_RELATION_REUSE,
        expected_error_fragment=(
            "seeded relation reuse requires an incremental or snapshot action"
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RELATION_REUSE_VALIDATION_TEST_CASES,
    ids=[case.description for case in RELATION_REUSE_VALIDATION_TEST_CASES],
)
def test_given_invalid_relation_reuse_plan_when_building_model_entry_then_it_raises(
    test_case: RelationReuseValidationTestCase,
) -> None:
    relation_reuse: RelationReusePlan = RelationReusePlan(
        kind=test_case.reuse_kind,
        origin=CompiledRelationLocation(
            database=None,
            schema="prod",
            name="orders",
            qualified_name="prod.orders",
        ),
        reuse_from_target_name="prod",
        hard_copy=True,
        fingerprint_database=None,
        fingerprint_schema="prod",
    )

    with pytest.raises(PlannerInputError) as exc_info:
        ModelPlanEntry(
            key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),
            name="orders",
            relative_path=Path("models/orders.sql"),
            materialization_type=test_case.materialization_type,
            action=test_case.action,
            reason=PlanReason.NO_CHANGE,
            destination=CompiledRelationLocation(
                database=None,
                schema="dev",
                name="orders",
                qualified_name="dev.orders",
            ),
            fingerprint_query_sql="SELECT 1 AS id",
            resolved_sql="SELECT 1 AS id",
            logical_ddl="CREATE TABLE dev.orders AS SELECT 1 AS id",
            incremental_strategy=(
                "append"
                if test_case.materialization_type == MaterializationType.INCREMENTAL
                else None
            ),
            relation_reuse=relation_reuse,
        )

    assert test_case.expected_error_fragment in str(exc_info.value)
