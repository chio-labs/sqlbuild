"""Read Python node identity observations from virtual state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.virtual.state.main.encoding.decode_state_text import decode_state_text
from sqlbuild.virtual.state.models import (
    PythonNodeVersionRecord,
    VirtualEnvironmentPythonNodeRefRecord,
)


def read_virtual_python_identity_fingerprints(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    virtual_environment_name: str,
) -> dict[tuple[str, str], Fingerprint]:
    """Return VDE-bound Python identities in the shared plan comparison shape."""

    result: dict[tuple[str, str], Fingerprint] = {}
    refs: tuple[VirtualEnvironmentPythonNodeRefRecord, ...] = (
        backend.get_virtual_environment_python_node_refs(
            connection=state_connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
        )
    )
    ref: VirtualEnvironmentPythonNodeRefRecord
    for ref in refs:
        record: PythonNodeVersionRecord | None = backend.get_python_node_version(
            connection=state_connection,
            schema=schema,
            node_type=ref.node_type,
            node_name=ref.node_name,
            version_hash=ref.version_hash,
        )
        if record is None:
            continue
        definition_json: str | None = decode_state_text(record.definition_json_b64)
        metadata_json: str | None = decode_state_text(record.identity_metadata_json_b64)
        if definition_json is None or metadata_json is None:
            continue
        result[(record.node_type, record.node_name)] = Fingerprint(
            node_type=record.node_type,
            node_name=record.node_name,
            target_database=None,
            target_schema=None,
            target_name=None,
            run_id="",
            definition_hash=record.definition_hash,
            version_hash=record.version_hash,
            schema_fingerprint="",
            definition=definition_json,
            metadata_json=metadata_json,
            ts=datetime.fromtimestamp(0, tz=UTC),
        )
    return result
