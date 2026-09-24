"""Model lifecycle hook serialization entrypoint."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.discovery._helpers.sql.hook_entries import serialize_hook_entries_impl


def serialize_hook_entries(
    *,
    value: object,
    sql_fields: tuple[str, ...],
    python_hook_fields: Mapping[str, Mapping[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Serialize resolved hook entries with an explicit SQL hook field allowlist."""

    return serialize_hook_entries_impl(
        value=value, sql_fields=sql_fields, python_hook_fields=python_hook_fields or {}
    )
