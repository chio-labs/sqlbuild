from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateLifecycleE2ETestCase:
    description: str
    expected_exit_code: int
    expected_init_fragment: str
    expected_migrate_fragment: str
    expected_rollback_fragment: str
    expected_reset_fragment: str
    expected_schema_version: int


@dataclass(frozen=True)
class StateLifecycleErrorE2ETestCase:
    description: str
    project_toml: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_error_fragment: str


@dataclass(frozen=True)
class StateLocalOverrideE2ETestCase:
    description: str
    expected_exit_code: int
    expected_schema_version: int


@dataclass(frozen=True)
class StateExplicitRollbackE2ETestCase:
    description: str
    expected_exit_code: int
    expected_rollback_fragment: str
    expected_schema_version: int


@dataclass(frozen=True)
class StateModeGuardE2ETestCase:
    description: str
    project_toml: str
    expected_exit_code: int
    expected_error_fragment: str
