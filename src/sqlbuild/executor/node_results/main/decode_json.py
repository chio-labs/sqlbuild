"""Public node result JSON decoding entrypoint."""

from __future__ import annotations

from sqlbuild.executor.node_results.helpers.serialization import decode_json_b64


def decode_node_result_json(value: str, *, label: str, node_name: str) -> object:
    """Decode a persisted node result JSON value."""

    return decode_json_b64(value, label=label, node_name=node_name)
