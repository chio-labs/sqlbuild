"""Version identity metadata comparison helpers."""

from __future__ import annotations

import json


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
    identity_payload.pop("audit_gate", None)
    return identity_payload
