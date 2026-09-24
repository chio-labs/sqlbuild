"""Source and managed-target schema overlap helpers."""

from __future__ import annotations

from sqlbuild.executor.janitor._helpers.plan import normalized_schema_key


def blocking_source_names(
    *,
    schema_key: tuple[str | None, str | None],
    managed_schema_keys: set[tuple[str | None, str | None]],
    source_schema_names: dict[tuple[str | None, str | None], set[str]],
) -> tuple[str, ...]:
    """Return active sources when one managed schema has mixed ownership."""

    normalized: tuple[str | None, str | None] = normalized_schema_key(schema_key)
    if not any(normalized_schema_key(candidate) == normalized for candidate in managed_schema_keys):
        return ()
    return tuple(
        sorted(
            source_names_for_schema(schema_key=schema_key, source_schema_names=source_schema_names)
        )
    )


def source_names_for_schema(
    *,
    schema_key: tuple[str | None, str | None],
    source_schema_names: dict[tuple[str | None, str | None], set[str]],
) -> set[str]:
    """Return active source names configured in one schema, compared case-insensitively."""

    normalized: tuple[str | None, str | None] = normalized_schema_key(schema_key)
    names: set[str] = set()
    for candidate, source_names in source_schema_names.items():
        if normalized_schema_key(candidate) == normalized:
            names.update(source_names)
    return names
