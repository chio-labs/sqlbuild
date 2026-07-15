"""Public scenario artifact physical-name detection entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.scenario.artifact_names import (
    is_scenario_artifact_physical_name as _is_scenario_artifact_physical_name,
)


def is_scenario_artifact_physical_name(name: str) -> bool:
    """Return whether a relation name matches SQLBuild's scenario artifact shape."""

    return _is_scenario_artifact_physical_name(name)
