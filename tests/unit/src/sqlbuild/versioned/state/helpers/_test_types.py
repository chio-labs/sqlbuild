from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.versioned.state.types import StateSchemaValidationIssueKind


@dataclass(frozen=True)
class StateValidationHelperTestCase:
    description: str
    existing_tables: set[str]
    columns_by_table: dict[str, dict[str, str]]
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
