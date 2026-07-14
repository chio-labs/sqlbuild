from __future__ import annotations

from typing import Any, cast

from sqlbuild.virtual.state.models import (
    PythonNodeVersionRecord,
    StateOperationEventRecord,
    StateOperationRecord,
    VirtualEnvironmentPythonNodeRefRecord,
)


class RecordingStateBackend:
    def __init__(self) -> None:
        self.operation: StateOperationRecord | None = None
        self.events: list[StateOperationEventRecord] = []

    def get_state_operation(
        self,
        *,
        connection: Any,
        schema: str,
        operation_id: str,
    ) -> StateOperationRecord | None:
        del connection, schema
        operations_by_id: dict[str, StateOperationRecord] = {
            getattr(self.operation, "operation_id", ""): cast(StateOperationRecord, self.operation)
        }
        return operations_by_id.get(operation_id)

    def upsert_state_operation(
        self,
        *,
        connection: Any,
        schema: str,
        record: StateOperationRecord,
    ) -> None:
        del connection, schema
        self.operation = record

    def create_state_operation_event(
        self,
        *,
        connection: Any,
        schema: str,
        record: StateOperationEventRecord,
    ) -> None:
        del connection, schema
        self.events.append(record)


class RecordingPythonIdentityStateBackend:
    def __init__(self) -> None:
        self.versions: dict[tuple[str, str, str], PythonNodeVersionRecord] = {}
        self.refs: dict[tuple[str, str, str], VirtualEnvironmentPythonNodeRefRecord] = {}

    def upsert_python_node_version(
        self, *, connection: Any, schema: str, record: PythonNodeVersionRecord
    ) -> None:
        del connection, schema
        self.versions[(record.node_type, record.node_name, record.version_hash)] = record

    def get_python_node_version(
        self,
        *,
        connection: Any,
        schema: str,
        node_type: str,
        node_name: str,
        version_hash: str,
    ) -> PythonNodeVersionRecord | None:
        del connection, schema
        return self.versions.get((node_type, node_name, version_hash))

    def upsert_virtual_environment_python_node_ref(
        self,
        *,
        connection: Any,
        schema: str,
        ref: VirtualEnvironmentPythonNodeRefRecord,
    ) -> None:
        del connection, schema
        self.refs[(ref.virtual_environment_name, ref.node_type, ref.node_name)] = ref

    def get_virtual_environment_python_node_refs(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentPythonNodeRefRecord, ...]:
        del connection, schema
        refs_by_environment: dict[str, list[VirtualEnvironmentPythonNodeRefRecord]] = {}
        key: tuple[str, str, str]
        ref: VirtualEnvironmentPythonNodeRefRecord
        for key, ref in sorted(self.refs.items()):
            refs_by_environment.setdefault(key[0], []).append(ref)
        return tuple(refs_by_environment.get(virtual_environment_name, ()))
