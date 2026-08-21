"""Polyglot decision-site identification."""

from __future__ import annotations

import json
from typing import Any

_COMPARISON_KINDS: frozenset[str] = frozenset({"eq", "neq", "gt", "gte", "lt", "lte"})
_DECISION_KEYS: frozenset[str] = frozenset({"having", "ifs", "on", "qualify", "where_clause"})


def decision_comparison_signatures(*, ast: Any) -> frozenset[str]:
    """Return stable payload signatures for comparisons under decision clauses."""

    signatures: set[str] = set()
    signatures = _collect_signatures(
        value=ast.to_dict(), inside_decision=False, signatures=signatures
    )
    return frozenset(signatures)


def comparison_signature(*, node: Any) -> str:
    """Return the stable payload signature for one Polyglot comparison node."""

    return json.dumps(node.to_dict(), sort_keys=True, separators=(",", ":"))


def _collect_signatures(*, value: object, inside_decision: bool, signatures: set[str]) -> set[str]:
    if isinstance(value, list):
        for item in value:
            signatures = _collect_signatures(
                value=item,
                inside_decision=inside_decision,
                signatures=signatures,
            )
        return signatures
    if not isinstance(value, dict):
        return signatures
    for key, child in value.items():
        child_is_decision: bool = inside_decision or key in _DECISION_KEYS
        if child_is_decision and key in _COMPARISON_KINDS:
            signatures.add(json.dumps({key: child}, sort_keys=True, separators=(",", ":")))
        signatures = _collect_signatures(
            value=child,
            inside_decision=child_is_decision,
            signatures=signatures,
        )
    return signatures
