"""Expand the shared nodes of a stage capture document."""

from __future__ import annotations

import json

from scripts.compiler_differential._helpers.comparing.compare import as_json_object, shared_digest
from scripts.compiler_differential.constants import (
    STAGE_CAPTURE_ROOT_KEY,
    STAGE_CAPTURE_SHARED_NODES_KEY,
)

_SHARED_DOCUMENT_KEYS: frozenset[str] = frozenset(
    {STAGE_CAPTURE_SHARED_NODES_KEY, STAGE_CAPTURE_ROOT_KEY}
)


def expand_capture_text(text: str) -> object:
    """Parse a whole capture document, replacing every shared reference by its node."""

    document: object = json.loads(text)
    mapping: dict[str, object] | None = as_json_object(document)
    nodes: dict[str, object] | None = as_json_object(
        None if mapping is None else mapping.get(STAGE_CAPTURE_SHARED_NODES_KEY)
    )
    if mapping is None or nodes is None or set(mapping) != _SHARED_DOCUMENT_KEYS:
        return document
    expanded: dict[str, object] = {}
    for digest, node in nodes.items():
        expanded[digest] = _expanded(value=node, nodes=expanded)
    return _expanded(value=mapping[STAGE_CAPTURE_ROOT_KEY], nodes=expanded)


def _expanded(*, value: object, nodes: dict[str, object]) -> object:
    digest: str | None = shared_digest(value)
    if digest is not None:
        return nodes[digest]
    items: dict[str, object] | None = as_json_object(value)
    if items is not None:
        return {key: _expanded(value=item, nodes=nodes) for key, item in items.items()}
    if isinstance(value, list):
        return [_expanded(value=item, nodes=nodes) for item in value]
    return value
