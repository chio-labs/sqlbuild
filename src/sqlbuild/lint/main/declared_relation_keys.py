"""Declared unique keys of project relations, for ranking determinism proofs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sqlbuild.lint.constants import (
    CURSOR_CONFIG,
    INCREMENTAL_MATERIALIZATION,
    INCREMENTAL_MODE_CONFIG,
    INCREMENTAL_STRATEGY_CONFIG,
    KEY_PRESERVING_STRATEGIES,
    KEYED_DELETE_INSERT_STRATEGY,
    MATERIALIZED_CONFIG,
    MICROBATCH_MODE,
    NOT_NULL_AUDIT_NAME,
    RELATION_IDENTITY_TEMPLATE,
    RELATION_KIND_REF,
    RELATION_KIND_SEED,
    UNIQUE_AUDIT_COLUMN_ARGUMENT,
    UNIQUE_AUDIT_NAME,
    UNIQUE_KEY_CONFIG,
)
from sqlbuild.lint.types import RelationKeys


def declared_relation_keys(
    *, relations: Iterable[tuple[str, str, object, Mapping[str, object]]]
) -> RelationKeys:
    """Collect keys that prove one row per key from `(kind, name, entry, config)` relations."""

    keys: dict[str, list[tuple[str, ...]]] = {}
    for kind, name, entry, values in relations:
        found: list[tuple[str, ...]] = _trusted_unique_key(values=values)
        found.extend((column,) for column in _non_null_unique_columns(entry=entry))
        if not found:
            continue
        kinds: tuple[str, ...] = (
            (kind, RELATION_KIND_REF) if kind == RELATION_KIND_SEED else (kind,)
        )
        for identity_kind in kinds:
            identity: str = RELATION_IDENTITY_TEMPLATE.format(kind=identity_kind, name=name)
            keys.setdefault(identity, []).extend(found)
    return {name: tuple(dict.fromkeys(found)) for name, found in sorted(keys.items())}


def _non_null_unique_columns(*, entry: object) -> list[str]:
    """Columns with a `unique` audit that are also non-null by audit or `nullable false`."""

    audited: dict[str, set[str]] = {UNIQUE_AUDIT_NAME: set(), NOT_NULL_AUDIT_NAME: set()}
    unique: list[str] = []
    for column in getattr(entry, "columns", None) or ():
        names: set[str] = {audit.definition_name for audit in getattr(column, "audits", None) or ()}
        if UNIQUE_AUDIT_NAME in names:
            unique.append(str(column.name))
        if NOT_NULL_AUDIT_NAME in names or getattr(column, "nullable", None) is False:
            audited[NOT_NULL_AUDIT_NAME].add(str(column.name).casefold())
    for audit in getattr(entry, "audits", None) or ():
        argument: object = audit.arguments.get(UNIQUE_AUDIT_COLUMN_ARGUMENT)
        if audit.definition_name in audited and isinstance(argument, str):
            audited[audit.definition_name].add(argument.casefold())
            if audit.definition_name == UNIQUE_AUDIT_NAME:
                unique.append(argument)
    return [column for column in unique if column.casefold() in audited[NOT_NULL_AUDIT_NAME]]


def _trusted_unique_key(*, values: Mapping[str, object]) -> list[tuple[str, ...]]:
    """`unique_key` only where the incremental strategy keeps one row per key."""

    strategy: str = str(values.get(INCREMENTAL_STRATEGY_CONFIG, "")).lower()
    trusted: bool = (
        str(values.get(MATERIALIZED_CONFIG, "")).lower() == INCREMENTAL_MATERIALIZATION
        and str(values.get(INCREMENTAL_MODE_CONFIG, "")).lower() != MICROBATCH_MODE
        and strategy in KEY_PRESERVING_STRATEGIES
        and not (strategy == KEYED_DELETE_INSERT_STRATEGY and values.get(CURSOR_CONFIG))
    )
    value: object = values.get(UNIQUE_KEY_CONFIG) if trusted else None
    if isinstance(value, str):
        return [(value,)]
    if isinstance(value, list | tuple) and value and all(isinstance(item, str) for item in value):
        return [tuple(str(item) for item in value)]
    return []
