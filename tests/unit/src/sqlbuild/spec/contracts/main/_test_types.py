from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.spec.contracts.models import (
    AuthoredTimeTravelRetention,
    ExecutionLimitsConfig,
    LoaderDestinationParts,
    LocalConfig,
    ProjectConfig,
)
from sqlbuild.sql_values.types import CollectionRendering


@dataclass(frozen=True)
class EffectiveCollectionRenderingResolutionTestCase:
    description: str
    project_config: ProjectConfig
    declaration_override: CollectionRendering | None
    expected_collection_rendering: CollectionRendering


@dataclass(frozen=True)
class TargetRetentionResolutionTestCase:
    description: str
    project_config: ProjectConfig
    local_config: LocalConfig
    target_name: str
    expected_default: AuthoredTimeTravelRetention | None
    expected_by_materialization: dict[str, AuthoredTimeTravelRetention] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class ExecutionLimitsResolutionTestCase:
    description: str
    project_config: ProjectConfig
    local_config: LocalConfig
    target_name: str
    expected_limits: ExecutionLimitsConfig


@dataclass(frozen=True)
class LoaderDestinationPartsTestCase:
    description: str
    destination: str
    default_database: str | None
    default_schema: str | None
    expected_parts: LoaderDestinationParts


@dataclass(frozen=True)
class InvalidLoaderDestinationTestCase:
    description: str
    destination: str
    expected_error_fragment: str
