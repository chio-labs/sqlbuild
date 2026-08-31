"""Source and managed-target schema overlap helpers."""

from __future__ import annotations


def blocking_source_names(
    *,
    schema_key: tuple[str | None, str | None],
    managed_schema_keys: set[tuple[str | None, str | None]],
    source_schema_names: dict[tuple[str | None, str | None], set[str]],
) -> tuple[str, ...]:
    """Return active sources when one managed schema has mixed ownership."""

    normalized: tuple[str | None, str | None] = _normalized_schema_key(schema_key)
    if not any(
        _normalized_schema_key(candidate) == normalized for candidate in managed_schema_keys
    ):
        return ()
    for candidate, source_names in source_schema_names.items():
        if _normalized_schema_key(candidate) == normalized:
            return tuple(sorted(source_names))
    return ()


def _normalized_schema_key(
    schema_key: tuple[str | None, str | None],
) -> tuple[str | None, str | None]:
    database, schema = schema_key
    return (
        None if database is None else database.lower(),
        None if schema is None else schema.lower(),
    )
