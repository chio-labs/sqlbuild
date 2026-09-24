"""Scenario artifact physical-name helper implementations."""

from __future__ import annotations

import re

from sqlbuild.adapter.relations.main.fit_artifact_logical_name import fit_artifact_logical_name
from sqlbuild.compiler.planner.constants import (
    SCENARIO_ARTIFACT_KINDS,
    SCENARIO_ARTIFACT_PREFIX,
    SCENARIO_HASH_PREFIX_LENGTH,
)
from sqlbuild.compiler.planner.models import ParsedScenarioArtifactName

_SCENARIO_ARTIFACT_NAME_RE: re.Pattern[str] = re.compile(
    rf"^{re.escape(SCENARIO_ARTIFACT_PREFIX)}"
    rf"(?P<hash_prefix>[0-9a-f]{{{SCENARIO_HASH_PREFIX_LENGTH}}})__"
    rf"(?P<kind>{'|'.join(SCENARIO_ARTIFACT_KINDS)})__"
    r"(?P<logical_name>.+)$"
)


def build_scenario_artifact_physical_name(
    *,
    hash_prefix: str,
    kind: str,
    logical_name: str,
    identifier_limit: int,
) -> str:
    fixed_prefix: str = f"{SCENARIO_ARTIFACT_PREFIX}{hash_prefix}__{kind}__"
    logical_part: str = fit_scenario_artifact_logical_name(
        logical_name=logical_name,
        fixed_prefix=fixed_prefix,
        identifier_limit=identifier_limit,
    )
    return f"{fixed_prefix}{logical_part}"


def parse_scenario_artifact_physical_name(name: str) -> ParsedScenarioArtifactName | None:
    match: re.Match[str] | None = _SCENARIO_ARTIFACT_NAME_RE.fullmatch(name)
    if match is None:
        return None
    return ParsedScenarioArtifactName(
        hash_prefix=match.group("hash_prefix"),
        kind=match.group("kind"),
        logical_name=match.group("logical_name"),
    )


def is_scenario_artifact_physical_name(name: str) -> bool:
    return parse_scenario_artifact_physical_name(name) is not None


def fit_scenario_artifact_logical_name(
    *, logical_name: str, fixed_prefix: str, identifier_limit: int
) -> str:
    return fit_artifact_logical_name(
        logical_name=logical_name,
        fixed_prefix=fixed_prefix,
        identifier_limit=identifier_limit,
        artifact_label="Scenario artifact",
    )
