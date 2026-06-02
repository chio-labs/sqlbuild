from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.spec.models.project import LocalConfig, ProjectConfig


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
