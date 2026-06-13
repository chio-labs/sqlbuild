"""Runtime node result JSON serialization helpers."""

from __future__ import annotations

import base64
import binascii
import json

from sqlbuild.executor.shared.exceptions import ExecutorInputError


def encode_json_b64(value: object, *, label: str, node_name: str) -> str:
    try:
        raw_json: str = json.dumps(value, sort_keys=True, separators=(",", ":"))
    except TypeError as error:
        raise ExecutorInputError(
            f"Python node '{node_name}' produced non-JSON-serializable {label}"
        ) from error
    return base64.b64encode(raw_json.encode("utf-8")).decode("ascii")


def decode_json_b64(value: str, *, label: str, node_name: str) -> object:
    try:
        raw_json: str = base64.b64decode(value.encode("ascii"), validate=True).decode("utf-8")
        return json.loads(raw_json)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExecutorInputError(
            f"Invalid persisted {label} for Python node '{node_name}': expected base64 JSON"
        ) from error
