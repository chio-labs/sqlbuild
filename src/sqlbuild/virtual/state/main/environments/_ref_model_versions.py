"""Public helper resolving model-version records for environment refs."""

from __future__ import annotations

from typing import Any

from sqlbuild.virtual.state.models import ModelVersionRecord, VirtualEnvironmentModelRefRecord


def read_ref_model_versions(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    refs: tuple[VirtualEnvironmentModelRefRecord, ...],
) -> dict[str, ModelVersionRecord | None]:
    """Return the model-version record bound by each ref, keyed by model name."""

    return {
        ref.model_name: backend.get_model_version(
            connection=state_connection,
            schema=schema,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        for ref in refs
    }
