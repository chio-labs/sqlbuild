"""Persist Python node identity observations in virtual state."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlbuild.compiler.python_nodes.models import PythonNodeIdentity
from sqlbuild.virtual.shared.helpers.encoding import encode_state_text
from sqlbuild.virtual.state.models import (
    PythonNodeVersionRecord,
    VirtualEnvironmentPythonNodeRefRecord,
)
from sqlbuild.virtual.state.types import ModelVersionStatus


def try_record_virtual_python_node_identity(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    virtual_environment_name: str,
    identity: PythonNodeIdentity | None,
    logger: logging.Logger | None = None,
) -> None:
    """Best-effort append/update of Python node identity state for one VDE."""

    if identity is None:
        return
    resolved_logger: logging.Logger = logger or logging.getLogger("sqlbuild.python_identity")
    try:
        backend.upsert_python_node_version(
            state_connection,
            schema=schema,
            record=PythonNodeVersionRecord(
                node_type=identity.node_type,
                node_name=identity.node_name,
                version_hash=identity.version_hash,
                definition_hash=identity.definition_hash,
                identity_metadata_hash=hashlib.sha256(
                    identity.metadata_json.encode("utf-8")
                ).hexdigest(),
                definition_json_b64=encode_state_text(identity.definition_json),
                identity_metadata_json_b64=encode_state_text(identity.metadata_json),
                status=ModelVersionStatus.READY,
            ),
        )
        backend.upsert_virtual_environment_python_node_ref(
            state_connection,
            schema=schema,
            ref=VirtualEnvironmentPythonNodeRefRecord(
                virtual_environment_name=virtual_environment_name,
                node_type=identity.node_type,
                node_name=identity.node_name,
                version_hash=identity.version_hash,
            ),
        )
    except Exception as exc:
        resolved_logger.warning(
            "virtual python identity write failed for '%s': %s",
            identity.node_name,
            exc,
        )
