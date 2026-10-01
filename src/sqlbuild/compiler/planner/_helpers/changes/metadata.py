"""Version identity metadata comparison helpers."""

from __future__ import annotations

import json

from sqlbuild.compiler.fingerprints.constants import AUDIT_GATE_METADATA_KEY
from sqlbuild.compiler.planner.constants import (
    LOCAL_FUNCTION_HASHES_METADATA_KEY,
    MIGRATION_FINGERPRINT_METADATA_KEY,
)


def version_identity_metadata_payload(metadata_json: str | None) -> object:
    """Return the fingerprint metadata payload that participates in version identity."""

    if metadata_json is None:
        return None
    try:
        payload: object = json.loads(metadata_json)
    except json.JSONDecodeError:
        return metadata_json
    if not isinstance(payload, dict):
        return None
    identity_payload: dict[str, object] = dict(payload)
    identity_payload.pop(AUDIT_GATE_METADATA_KEY, None)
    identity_payload.pop(MIGRATION_FINGERPRINT_METADATA_KEY, None)
    return identity_payload


def non_function_identity_metadata_payload(metadata_json: str | None) -> object:
    """Return the version identity metadata payload without called-function hashes."""

    payload: object = version_identity_metadata_payload(metadata_json)
    if not isinstance(payload, dict):
        return payload
    return {
        key: value for key, value in payload.items() if key != LOCAL_FUNCTION_HASHES_METADATA_KEY
    }


def changed_local_function_names(
    *, metadata_json: str, previous_metadata_json: str
) -> tuple[str, ...]:
    """Return directly called functions whose recorded definition hash changed."""

    current: dict[str, object] = _local_function_hashes(metadata_json)
    previous: dict[str, object] = _local_function_hashes(previous_metadata_json)
    return tuple(
        sorted(
            name
            for name, function_hash in current.items()
            if name in previous and previous[name] != function_hash
        )
    )


def _local_function_hashes(metadata_json: str) -> dict[str, object]:
    try:
        payload: object = json.loads(metadata_json)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    hashes: object = payload.get(LOCAL_FUNCTION_HASHES_METADATA_KEY)
    return {str(name): value for name, value in hashes.items()} if isinstance(hashes, dict) else {}
