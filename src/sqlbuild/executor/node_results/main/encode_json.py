"""Public node result JSON encoding entrypoint."""

from __future__ import annotations

from sqlbuild.executor.node_results.helpers.serialization import encode_json_b64


def encode_node_result_json(*, value: object, label: str, node_name: str) -> str:
    """Encode a node result JSON value for persisted storage."""

    return encode_json_b64(value=value, label=label, node_name=node_name)
