"""Polyglot AST traversal and payload helpers for kata rules."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

from sqlbuild.kata_engine.constants import AST_SELECT_KIND, NAMED_CTE_TUPLE_SIZE


def payload(node: Any) -> dict[str, object]:
    """Return the single expression payload from a Polyglot node."""

    raw: object = node.to_dict()
    if not isinstance(raw, dict) or len(raw) != 1:
        return {}
    value: object = next(iter(raw.values()))
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def kind(node: Any) -> str:
    """Return a stable lowercase Polyglot node kind."""

    return str(getattr(node, "key", "") or getattr(node, "kind", "")).lower()


def nodes(*, root: Any, wanted: str) -> Iterator[Any]:
    """Yield every node whose stable kind matches wanted."""

    for node in root.walk():
        if kind(node) == wanted:
            yield node


def name_value(value: object) -> str:
    """Extract a name from Polyglot's nested name payload."""

    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        mapping: dict[str, object] = cast(dict[str, object], value)
        raw: object = mapping.get("name")
        if isinstance(raw, str):
            return raw
        if isinstance(raw, dict):
            return name_value(raw)
    return ""


def table_parts(node: Any) -> tuple[str, str, str]:
    """Return catalog, schema, and name for one table node."""

    data: dict[str, object] = payload(node)
    return (
        name_value(data.get("catalog")),
        name_value(data.get("schema")),
        name_value(data.get("name")),
    )


def cte_name(node: Any) -> str:
    if isinstance(node, tuple) and len(node) == NAMED_CTE_TUPLE_SIZE:
        return str(node[0])
    return str(getattr(node, "alias_or_name", "") or getattr(node, "name", ""))


def top_level_ctes(root: Any) -> tuple[Any, ...]:
    """Return top-level CTE nodes in authored order."""

    data: dict[str, object] = payload(root)
    with_payload: object = data.get("with")
    raw_ctes: object = (
        cast(dict[str, object], with_payload).get("ctes")
        if isinstance(with_payload, dict)
        else None
    )
    if not isinstance(raw_ctes, list):
        return ()
    candidates: tuple[Any, ...] = tuple(root.walk())
    matched_ids: set[int] = set()
    ctes: list[tuple[str, Any]] = []
    for raw_cte in raw_ctes:
        if not isinstance(raw_cte, dict):
            return ()
        cte_mapping: dict[str, object] = cast(dict[str, object], raw_cte)
        alias: str = name_value(cte_mapping.get("alias"))
        raw_body: object = cte_mapping.get("this")
        body: Any | None = None
        for candidate in candidates:
            if id(candidate) in matched_ids or candidate is root:
                continue
            if candidate.to_dict() == raw_body:
                body = candidate
                matched_ids.add(id(candidate))
                break
        if not alias or body is None:
            return ()
        ctes.append((alias, body))
    return tuple(ctes)


def select_payload(node: Any) -> dict[str, object]:
    return payload(node) if kind(node) == AST_SELECT_KIND else {}
