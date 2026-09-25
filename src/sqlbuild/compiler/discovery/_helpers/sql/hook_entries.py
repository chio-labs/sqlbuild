"""Serialization of resolved model lifecycle hook entries."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.discovery.models import PythonHookEntry, SqlHookEntry


def serialize_hook_entries_impl(
    *,
    value: object,
    sql_fields: tuple[str, ...],
    python_hook_fields: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    """Serialize resolved hook entries, keeping only the requested SQL hook fields."""

    if not isinstance(value, list | tuple):
        return []
    hooks: list[dict[str, object]] = []
    entry: object
    for entry in value:
        if isinstance(entry, SqlHookEntry):
            hooks.append(_serialize_sql_hook(entry=entry, sql_fields=sql_fields))
        elif isinstance(entry, PythonHookEntry):
            python_hook: dict[str, object] = {
                "type": "python",
                "name": entry.name,
                "kwargs": entry.kwargs,
            }
            python_hook.update(python_hook_fields.get(entry.name, {}))
            hooks.append(python_hook)
    return hooks


def _serialize_sql_hook(*, entry: SqlHookEntry, sql_fields: tuple[str, ...]) -> dict[str, object]:
    field_values: dict[str, object | None] = {
        "statement": entry.statement,
        "name": entry.name,
        "relative_path": (
            entry.relative_path.as_posix() if entry.relative_path is not None else None
        ),
        "definition_sql": entry.definition_sql,
        "kwargs": entry.kwargs,
        "description": entry.description,
    }
    hook: dict[str, object] = {"type": "sql"}
    field_name: str
    for field_name in sql_fields:
        field_value: object | None = field_values[field_name]
        if field_value is not None:
            hook[field_name] = field_value
    return hook
