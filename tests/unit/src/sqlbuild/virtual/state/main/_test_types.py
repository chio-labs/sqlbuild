from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.virtual.state.types import StateOperationStatus, StateOperationType


@dataclass(frozen=True)
class RecordStateOperationTestCase:
    description: str
    operation_id: str
    operation_type: StateOperationType
    virtual_environment_name: str
    start_message: str
    finish_message: str
    expected_final_status: StateOperationStatus
    expected_event_rows: tuple[tuple[str, StateOperationStatus, str], ...]


@dataclass(frozen=True)
class VirtualPythonNodeIdentityTestCase:
    description: str
    virtual_environment_name: str
    expected_node_type: str
    expected_node_name: str
    expected_version_hash: str
    expected_definition_json: str
    expected_metadata_json: str
