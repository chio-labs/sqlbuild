"""Version identity metadata comparison helpers."""

from __future__ import annotations

import json

from sqlbuild.compiler.compile.constants import CURSOR_INPUTS_CONFIG_KEY
from sqlbuild.compiler.fingerprints.constants import AUDIT_GATE_METADATA_KEY
from sqlbuild.compiler.planner.constants import (
    DECLARED_COLUMNS_METADATA_KEY,
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
    identity_payload.pop(DECLARED_COLUMNS_METADATA_KEY, None)
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


def with_origin_cursor_input_names(*, metadata_json: str, renamed_refs: dict[str, str]) -> str:
    """Return metadata JSON whose cursor_inputs name renamed models by their origin names."""

    try:
        payload: object = json.loads(metadata_json)
    except json.JSONDecodeError:
        return metadata_json
    config: object = payload.get("config") if isinstance(payload, dict) else None
    cursor_inputs: object = (
        config.get(CURSOR_INPUTS_CONFIG_KEY) if isinstance(config, dict) else None
    )
    if (
        not isinstance(payload, dict)
        or not isinstance(config, dict)
        or not isinstance(cursor_inputs, dict)
    ):
        return metadata_json
    origin_inputs: dict[str, object] = {
        renamed_refs.get(str(name), str(name)): value for name, value in cursor_inputs.items()
    }
    return json.dumps(
        {**payload, "config": {**config, CURSOR_INPUTS_CONFIG_KEY: origin_inputs}},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def recorded_declared_columns_hash(metadata_json: str | None) -> str | None:
    """Return the declared-columns hash a fingerprint row recorded, if it has one."""

    if metadata_json is None:
        return None
    try:
        payload: object = json.loads(metadata_json)
    except json.JSONDecodeError:
        return None
    value: object = (
        payload.get(DECLARED_COLUMNS_METADATA_KEY) if isinstance(payload, dict) else None
    )
    return value if isinstance(value, str) else None


def with_declared_columns_hash(*, metadata_json: str, declared_columns_hash: str) -> str:
    """Return fingerprint metadata JSON that also records the model's declared-columns hash."""

    try:
        payload: object = json.loads(metadata_json)
    except json.JSONDecodeError:
        return metadata_json
    if not isinstance(payload, dict):
        return metadata_json
    return json.dumps(
        {**payload, DECLARED_COLUMNS_METADATA_KEY: declared_columns_hash},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def without_declared_columns_hash(metadata_json: str) -> str:
    """Return fingerprint metadata JSON without the declared-columns hash key, if present."""

    try:
        payload: object = json.loads(metadata_json)
    except json.JSONDecodeError:
        return metadata_json
    if not isinstance(payload, dict) or DECLARED_COLUMNS_METADATA_KEY not in payload:
        return metadata_json
    return json.dumps(
        {key: value for key, value in payload.items() if key != DECLARED_COLUMNS_METADATA_KEY},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
