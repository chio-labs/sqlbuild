from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.state.types import StateSchemaValidationIssueKind


@dataclass(frozen=True)
class StateValidationHelperTestCase:
    description: str
    existing_tables: set[str]
    columns_by_table: dict[str, dict[str, str]]
    existing_indexes_by_table: dict[str, set[str]]
    expected_issue_kinds: tuple[StateSchemaValidationIssueKind, ...]


@dataclass(frozen=True)
class StateBackendConfigResolutionTestCase:
    description: str
    discovered_inputs: DiscoveredProjectInputs
    expected_backend: str
    expected_schema: str
    expected_database_suffix: str
    expected_allow_reset: bool


@dataclass(frozen=True)
class StateBackendConfigResolutionErrorTestCase:
    description: str
    discovered_inputs: DiscoveredProjectInputs
    expected_error_type: type[Exception]
    expected_message_fragment: str


@dataclass(frozen=True)
class StateLockServiceTestCase:
    description: str
    schema: str
    owner_id: str
    now: datetime
    ttl: timedelta
    expected_virtual_environment_lock_key: str
    expected_model_version_lock_key: str
    expected_state_migration_lock_key: str
