from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig
from sqlbuild.sql_values.types import CollectionRendering


@dataclass(frozen=True)
class TargetConfigResolutionTestCase:
    description: str
    project_config: ProjectConfig
    local_config: LocalConfig
    target_name: str
    expected_backend: str | None
    expected_schema: str | None
    expected_connection: dict[str, object]
    expected_allow_reset: bool
    expected_loader_schema: str | None = None
    expected_defer_clone_from: str | None = None
    expected_changes_only: bool | None = None
    expected_connection_name: str | None = None


@dataclass(frozen=True)
class EffectiveChangesOnlyResolutionTestCase:
    description: str
    project_config: ProjectConfig
    local_config: LocalConfig
    cli_changes_only: bool
    expected_changes_only: bool


@dataclass(frozen=True)
class EffectiveCollectionRenderingResolutionTestCase:
    description: str
    project_config: ProjectConfig
    declaration_override: CollectionRendering | None
    expected_collection_rendering: CollectionRendering
