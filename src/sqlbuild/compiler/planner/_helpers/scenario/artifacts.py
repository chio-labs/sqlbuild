"""Deterministic physical artifact naming for SQL scenarios."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.planner.constants import (
    SCENARIO_DEFAULT_IDENTIFIER_LIMIT,
    SCENARIO_HASH_PREFIX_LENGTH,
    SCENARIO_PLAN_HASH_COLLISION,
    SCENARIO_PLAN_INVALID_HASH_PREFIX,
    SCENARIO_PLAN_RELATION_COLLISION,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.planning.build_scenario_artifact_physical_name import (
    build_scenario_artifact_physical_name,
)
from sqlbuild.compiler.planner.models import (
    ScenarioArtifactIdentity,
    ScenarioArtifactName,
    ScenarioRelationMap,
)
from sqlbuild.compiler.planner.types import ScenarioArtifactKind


def compute_scenario_hash_prefix(
    *,
    project_name: str,
    scenario_name: str,
    prefix_length: int = SCENARIO_HASH_PREFIX_LENGTH,
) -> str:
    """Return a stable scenario artifact hash prefix."""

    if prefix_length < 1:
        raise PlannerInputError(
            "Scenario hash prefix length must be at least 1",
            code=SCENARIO_PLAN_INVALID_HASH_PREFIX,
        )
    hash_input: str = f"{project_name}:{scenario_name}"
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:prefix_length]


def build_scenario_hash_index(
    *,
    project_name: str,
    scenarios: tuple[CompiledSqlScenario, ...],
    prefix_length: int = SCENARIO_HASH_PREFIX_LENGTH,
) -> dict[str, str]:
    """Return scenario name to hash prefix, failing clearly on prefix collisions."""

    by_prefix: dict[str, CompiledSqlScenario] = {}
    result: dict[str, str] = {}
    scenario: CompiledSqlScenario
    for scenario in scenarios:
        prefix: str = compute_scenario_hash_prefix(
            project_name=project_name,
            scenario_name=scenario.name,
            prefix_length=prefix_length,
        )
        existing: CompiledSqlScenario | None = by_prefix.get(prefix)
        if existing is not None:
            raise PlannerInputError(
                "Scenario artifact hash collision: scenarios "
                f"'{existing.name}' and '{scenario.name}' both map to hash prefix "
                f"'{prefix}'. Rename one scenario file so SQLBuild can generate "
                "distinct warehouse artifact prefixes.",
                code=SCENARIO_PLAN_HASH_COLLISION,
                help=(
                    "Rename one scenario file so SQLBuild can generate distinct artifact prefixes."
                ),
            )
        by_prefix[prefix] = scenario
        result[scenario.name] = prefix
    return result


def build_scenario_artifact_name(
    *,
    hash_prefix: str,
    kind: ScenarioArtifactKind | str,
    logical_name: str,
    identifier_limit: int = SCENARIO_DEFAULT_IDENTIFIER_LIMIT,
) -> str:
    """Build one deterministic scenario physical relation name."""

    normalized_kind: ScenarioArtifactKind = ScenarioArtifactKind(kind)
    return build_scenario_artifact_physical_name(
        hash_prefix=hash_prefix,
        kind=normalized_kind.value,
        logical_name=logical_name,
        identifier_limit=identifier_limit,
    )


def build_scenario_relation_map(
    *,
    scenario_name: str,
    hash_prefix: str,
    artifacts: tuple[ScenarioArtifactIdentity, ...],
    identifier_limit: int = SCENARIO_DEFAULT_IDENTIFIER_LIMIT,
    normalize_identifier: Callable[[str], str] | None = None,
) -> ScenarioRelationMap:
    """Build and collision-check physical relation names for one scenario."""

    normalizer: Callable[[str], str] = normalize_identifier or (lambda value: value)
    resolved_artifacts: list[ScenarioArtifactName] = []
    seen: dict[str, ScenarioArtifactIdentity] = {}
    artifact: ScenarioArtifactIdentity
    for artifact in artifacts:
        physical_name: str = build_scenario_artifact_name(
            hash_prefix=hash_prefix,
            kind=artifact.kind,
            logical_name=artifact.logical_name,
            identifier_limit=identifier_limit,
        )
        normalized_physical_name: str = normalizer(physical_name)
        existing: ScenarioArtifactIdentity | None = seen.get(normalized_physical_name)
        if existing is not None:
            raise PlannerInputError(
                f"Scenario relation name collision in scenario '{scenario_name}'. "
                f"Both scenario artifacts map to '{physical_name}': "
                f"{ScenarioArtifactKind(existing.kind).value} {existing.logical_name} and "
                f"{ScenarioArtifactKind(artifact.kind).value} {artifact.logical_name}. "
                "Rename one artifact "
                "or shorten one model/source name.",
                code=SCENARIO_PLAN_RELATION_COLLISION,
                help="Rename or shorten one of the colliding scenario artifacts.",
            )
        seen[normalized_physical_name] = artifact
        resolved_artifacts.append(
            ScenarioArtifactName(identity=artifact, physical_name=physical_name)
        )

    return ScenarioRelationMap(
        scenario_name=scenario_name,
        hash_prefix=hash_prefix,
        artifacts=tuple(resolved_artifacts),
    )
