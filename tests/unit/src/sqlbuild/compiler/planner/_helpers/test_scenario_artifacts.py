from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.scenario.artifact_names import (
    parse_scenario_artifact_physical_name,
)
from sqlbuild.compiler.planner._helpers.scenario.artifacts import (
    build_scenario_artifact_name,
    build_scenario_hash_index,
    build_scenario_relation_map,
    compute_scenario_hash_prefix,
)
from sqlbuild.compiler.planner.constants import (
    SCENARIO_PLAN_HASH_COLLISION,
    SCENARIO_PLAN_RELATION_COLLISION,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.scenarios.is_scenario_artifact_physical_name import (
    is_scenario_artifact_physical_name,
)
from sqlbuild.compiler.planner.models import (
    ParsedScenarioArtifactName,
    ScenarioArtifactIdentity,
    ScenarioArtifactName,
    ScenarioRelationMap,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    ScenarioArtifactNameRecognitionTestCase,
    ScenarioArtifactNameTestCase,
    ScenarioHashCollisionTestCase,
    ScenarioHashPrefixTestCase,
    ScenarioRelationMapErrorTestCase,
    ScenarioRelationMapTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import (
    build_compiled_scenario_with_name,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioHashPrefixTestCase(
            description="uses stable project and scenario identity hash",
            project_name="waffle_shop",
            scenario_name="revenue__customer_refund",
            expected_hash_prefix="51b385aebe20",
        ),
        ScenarioHashPrefixTestCase(
            description="differs for different scenario names",
            project_name="waffle_shop",
            scenario_name="revenue__discount_edge_case",
            expected_hash_prefix="1c1eb75fd876",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_and_scenario_when_hashing_then_returns_expected_prefix(
    test_case: ScenarioHashPrefixTestCase,
) -> None:
    result: str = compute_scenario_hash_prefix(
        project_name=test_case.project_name,
        scenario_name=test_case.scenario_name,
    )

    assert result == test_case.expected_hash_prefix


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioHashCollisionTestCase(
            description="raises when hash prefixes collide",
            scenario_names=("scenario_2", "scenario_5"),
            prefix_length=1,
            expected_error_fragment="both map to hash prefix '9'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_colliding_scenario_hashes_when_building_index_then_raises_clear_error(
    test_case: ScenarioHashCollisionTestCase,
) -> None:
    with pytest.raises(PlannerInputError, match=test_case.expected_error_fragment) as exc_info:
        build_scenario_hash_index(
            project_name="waffle_shop",
            scenarios=tuple(
                build_compiled_scenario_with_name(name) for name in test_case.scenario_names
            ),
            prefix_length=test_case.prefix_length,
        )
    assert exc_info.value.code == SCENARIO_PLAN_HASH_COLLISION


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioArtifactNameTestCase(
            description="preserves short logical model name",
            hash_prefix="51b385aebe20",
            kind="model",
            logical_name="daily_revenue",
            identifier_limit=63,
            expected_physical_name="__sqb_51b385aebe20__model__daily_revenue",
        ),
        ScenarioArtifactNameTestCase(
            description="shortens long logical model name deterministically",
            hash_prefix="51b385aebe20",
            kind="model",
            logical_name="very_long_customer_revenue_reconciliation_by_region_and_day",
            identifier_limit=63,
            expected_physical_name=(
                "__sqb_51b385aebe20__model__very_long_customer_revenue__f3f1eed0"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_scenario_artifact_when_building_name_then_returns_expected_physical_name(
    test_case: ScenarioArtifactNameTestCase,
) -> None:
    result: str = build_scenario_artifact_name(
        hash_prefix=test_case.hash_prefix,
        kind=test_case.kind,
        logical_name=test_case.logical_name,
        identifier_limit=test_case.identifier_limit,
    )

    assert result == test_case.expected_physical_name
    assert len(result) <= test_case.identifier_limit


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioArtifactNameRecognitionTestCase(
            description="recognizes generated source artifact name",
            physical_name=build_scenario_artifact_name(
                hash_prefix="51b385aebe20",
                kind="source",
                logical_name="raw__orders",
            ),
            expected_is_scenario_artifact=True,
            expected_hash_prefix="51b385aebe20",
            expected_kind="source",
            expected_logical_name="raw__orders",
        ),
        ScenarioArtifactNameRecognitionTestCase(
            description="recognizes generated shortened model artifact name",
            physical_name=build_scenario_artifact_name(
                hash_prefix="51b385aebe20",
                kind="model",
                logical_name="very_long_customer_revenue_reconciliation_by_region_and_day",
                identifier_limit=63,
            ),
            expected_is_scenario_artifact=True,
            expected_hash_prefix="51b385aebe20",
            expected_kind="model",
            expected_logical_name="very_long_customer_revenue__f3f1eed0",
        ),
        ScenarioArtifactNameRecognitionTestCase(
            description="recognizes generated dbt ref artifact name",
            physical_name=build_scenario_artifact_name(
                hash_prefix="51b385aebe20",
                kind="dbt_ref",
                logical_name="stripe__payments",
            ),
            expected_is_scenario_artifact=True,
            expected_hash_prefix="51b385aebe20",
            expected_kind="dbt_ref",
            expected_logical_name="stripe__payments",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_physical_name_when_parsing_scenario_artifact_then_returns_expected_parts(
    test_case: ScenarioArtifactNameRecognitionTestCase,
) -> None:
    parsed: ParsedScenarioArtifactName | None = parse_scenario_artifact_physical_name(
        test_case.physical_name
    )

    assert is_scenario_artifact_physical_name(test_case.physical_name) is (
        test_case.expected_is_scenario_artifact
    )
    assert parsed is not None
    assert parsed.hash_prefix == test_case.expected_hash_prefix
    assert parsed.kind == test_case.expected_kind
    assert parsed.logical_name == test_case.expected_logical_name


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioArtifactNameRecognitionTestCase(
            description="rejects non-12-character hash prefix",
            physical_name="__sqb_51b385aebe2__model__daily_revenue",
            expected_is_scenario_artifact=False,
        ),
        ScenarioArtifactNameRecognitionTestCase(
            description="rejects unknown artifact kind",
            physical_name="__sqb_51b385aebe20__cmp__daily_revenue",
            expected_is_scenario_artifact=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_scenario_physical_name_when_parsing_scenario_artifact_then_returns_none(
    test_case: ScenarioArtifactNameRecognitionTestCase,
) -> None:
    parsed: ParsedScenarioArtifactName | None = parse_scenario_artifact_physical_name(
        test_case.physical_name
    )

    assert is_scenario_artifact_physical_name(test_case.physical_name) is (
        test_case.expected_is_scenario_artifact
    )
    assert parsed is None


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioRelationMapTestCase(
            description="builds relation map for source ref and model artifacts",
            artifacts=(
                ScenarioArtifactIdentity(kind="source", logical_name="raw__orders"),
                ScenarioArtifactIdentity(kind="ref", logical_name="stg_customers"),
                ScenarioArtifactIdentity(kind="model", logical_name="daily_revenue"),
            ),
            expected_relation_map=ScenarioRelationMap(
                scenario_name="revenue__customer_refund",
                hash_prefix="51b385aebe20",
                artifacts=(
                    ScenarioArtifactName(
                        identity=ScenarioArtifactIdentity(
                            kind="source", logical_name="raw__orders"
                        ),
                        physical_name="__sqb_51b385aebe20__source__raw__orders",
                    ),
                    ScenarioArtifactName(
                        identity=ScenarioArtifactIdentity(kind="ref", logical_name="stg_customers"),
                        physical_name="__sqb_51b385aebe20__ref__stg_customers",
                    ),
                    ScenarioArtifactName(
                        identity=ScenarioArtifactIdentity(
                            kind="model", logical_name="daily_revenue"
                        ),
                        physical_name="__sqb_51b385aebe20__model__daily_revenue",
                    ),
                ),
            ),
            normalize_identifier=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scenario_artifacts_when_building_relation_map_then_returns_expected_map(
    test_case: ScenarioRelationMapTestCase,
) -> None:
    result: ScenarioRelationMap = build_scenario_relation_map(
        scenario_name="revenue__customer_refund",
        hash_prefix="51b385aebe20",
        artifacts=test_case.artifacts,
        normalize_identifier=test_case.normalize_identifier,
    )

    assert result == test_case.expected_relation_map


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioRelationMapErrorTestCase(
            description="raises on duplicate physical relation names",
            artifacts=(
                ScenarioArtifactIdentity(kind="model", logical_name="daily_revenue"),
                ScenarioArtifactIdentity(kind="model", logical_name="daily_revenue"),
            ),
            expected_error_fragment="relation name collision",
            normalize_identifier=None,
        ),
        ScenarioRelationMapErrorTestCase(
            description="raises on adapter normalized collision",
            artifacts=(
                ScenarioArtifactIdentity(kind="model", logical_name="Daily_Revenue"),
                ScenarioArtifactIdentity(kind="model", logical_name="daily_revenue"),
            ),
            expected_error_fragment="relation name collision",
            normalize_identifier=str.lower,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_colliding_scenario_artifacts_when_building_relation_map_then_raises(
    test_case: ScenarioRelationMapErrorTestCase,
) -> None:
    with pytest.raises(PlannerInputError, match=test_case.expected_error_fragment) as exc_info:
        build_scenario_relation_map(
            scenario_name="revenue__customer_refund",
            hash_prefix="51b385aebe20",
            artifacts=test_case.artifacts,
            normalize_identifier=test_case.normalize_identifier,
        )
    assert exc_info.value.code == SCENARIO_PLAN_RELATION_COLLISION
