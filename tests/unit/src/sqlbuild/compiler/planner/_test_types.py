from dataclasses import dataclass

from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, RelationReuseKind


@dataclass(frozen=True)
class RelationReuseValidationTestCase:
    description: str
    materialization_type: MaterializationType
    action: PlanAction
    reuse_kind: RelationReuseKind
    expected_error_fragment: str
