"""Public scenario artifact physical-name builder entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.scenario.artifact_names import (
    build_scenario_artifact_physical_name as _build_scenario_artifact_physical_name,
)


def build_scenario_artifact_physical_name(
    *, hash_prefix: str, kind: str, logical_name: str, identifier_limit: int
) -> str:
    """Build one deterministic scenario artifact physical relation name."""

    return _build_scenario_artifact_physical_name(
        hash_prefix=hash_prefix,
        kind=kind,
        logical_name=logical_name,
        identifier_limit=identifier_limit,
    )
