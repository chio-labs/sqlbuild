"""Top-level CTEs and direct tables of Polyglot wheel trees, for resolved column reads."""

from __future__ import annotations

from typing import Any, cast

from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_ANNOTATED as _POLYGLOT_KIND_ANNOTATED,
)
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_KIND_TABLE as _POLYGLOT_KIND_TABLE
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_PAYLOAD_NAME as _POLYGLOT_PAYLOAD_NAME


def _polyglot_top_level_ctes(root: Any) -> tuple[tuple[str, Any, bool], ...]:
    targeted_ctes: object = getattr(root, "with_ctes", None)
    if callable(targeted_ctes):
        values: object = targeted_ctes()
        if isinstance(values, list):
            return tuple(
                (str(name), body, bool(has_column_alias)) for name, has_column_alias, body in values
            )
    with_payload: object = root.arg("with")
    raw_ctes: object = (
        cast(dict[str, object], with_payload).get("ctes")
        if isinstance(with_payload, dict)
        else None
    )
    if not isinstance(raw_ctes, list):
        return ()
    children: tuple[Any, ...] = tuple(root.children())
    if len(children) < len(raw_ctes):
        return ()
    cte_bodies: tuple[Any, ...] = children[-len(raw_ctes) :]
    ctes: list[tuple[str, Any, bool]] = []
    for raw_cte, body in zip(raw_ctes, cte_bodies, strict=True):
        if not isinstance(raw_cte, dict):
            return ()
        cte_payload: dict[str, object] = cast(dict[str, object], raw_cte)
        cte_name: str = _polyglot_name_payload_value(cte_payload.get("alias"))
        if not cte_name:
            return ()
        columns: object = cte_payload.get("columns")
        ctes.append((cte_name, body, isinstance(columns, list) and bool(columns)))
    return tuple(ctes)


def _polyglot_direct_select_tables(select: Any) -> tuple[Any, ...]:
    return tuple(
        child
        for child in select.children()
        if str(getattr(child, "kind", "")) == _POLYGLOT_KIND_TABLE
    )


def _unwrap_polyglot_annotations(expression: Any) -> Any:
    while str(getattr(expression, "kind", "")) == _POLYGLOT_KIND_ANNOTATED:
        expression = expression.this
    return expression


def _polyglot_name_payload_value(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""
    name: object = cast(dict[str, object], payload).get(_POLYGLOT_PAYLOAD_NAME)
    return name if isinstance(name, str) else ""
