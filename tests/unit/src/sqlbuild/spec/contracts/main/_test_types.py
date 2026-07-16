from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


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
    expected_reuse_from: str | None = None
    expected_defer_clone_from: str | None = None
    expected_force: bool | None = None
    expected_reuse_hard_copy: bool = False


@dataclass(frozen=True)
class EffectiveForceResolutionTestCase:
    description: str
    project_config: ProjectConfig
    local_config: LocalConfig
    cli_force: bool
    expected_force: bool


@dataclass(frozen=True)
class TargetConfigReuseErrorTestCase:
    description: str
    target_name: str
    reuse_from: str
    expected_error_fragment: str


@dataclass(frozen=True)
class TargetConfigReuseLocalSourceTestCase:
    description: str
    expected_reuse_from: str
