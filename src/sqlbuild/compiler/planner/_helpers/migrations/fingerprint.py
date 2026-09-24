"""Local migration fingerprints that identify the same table across renames."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from sqlbuild.compiler.compile.constants import CURSOR_INPUTS_CONFIG_KEY
from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.planner._helpers.changes.metadata import version_identity_metadata_payload
from sqlbuild.compiler.planner.constants import (
    MIGRATION_FINGERPRINT_EXCLUDED_CONFIG_KEYS,
    MIGRATION_LOCAL_NAME_PREFIX,
    MIGRATION_MODEL_NAME_METADATA_KEY,
    MIGRATION_REF_PLACEHOLDER_PREFIX,
)
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql

_REF_MARKER: re.Pattern[str] = re.compile(r"""__ref\(\s*(?:"([^"]+)"|'([^']+)')\s*\)""")
_IDENTIFIER_NAME_KEY: str = "name"
_IDENTIFIER_QUOTED_KEY: str = "quoted"
_ALIAS_KEY: str = "alias"
_WITH_KEY: str = "with"
_CTES_KEY: str = "ctes"
_SPAN_KEY: str = "span"
_COMMENTS_SUFFIX: str = "comments"
_CONFIG_KEY: str = "config"
_GENERIC_DIALECT: str = "generic"
_TABLE_KEY: str = "table"
_ALIASED_RELATION_KEYS: frozenset[str] = frozenset({_TABLE_KEY, "subquery"})
_QUALIFIED_REFERENCE_KEYS: frozenset[str] = frozenset({"column", "star"})
_RELATION_QUALIFIER_KEYS: tuple[str, ...] = ("schema", "catalog")


def build_migration_fingerprint(
    *,
    query_sql: str,
    metadata_json: str,
    ref_identities: Mapping[str, str],
    dialect: str | None,
) -> str | None:
    """Hash normalized SQL and non-storage metadata with refs resolved through renames."""

    normalized_sql: str | None = _normalized_query_sql(
        query_sql=query_sql, ref_identities=ref_identities, dialect=dialect
    )
    if normalized_sql is None:
        return None
    payload: str = json.dumps(
        {
            "metadata": _identity_metadata(
                metadata_json=metadata_json, ref_identities=ref_identities
            ),
            "sql": normalized_sql,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _identity_metadata(*, metadata_json: str, ref_identities: Mapping[str, str]) -> Any:
    payload: Any = version_identity_metadata_payload(metadata_json)
    if not isinstance(payload, dict):
        return payload
    identity: dict[str, Any] = {str(key): value for key, value in payload.items()}
    _ = identity.pop(MIGRATION_MODEL_NAME_METADATA_KEY, None)
    config: Any = identity.get(_CONFIG_KEY)
    if isinstance(config, dict):
        identity[_CONFIG_KEY] = {
            key: _resolved_cursor_inputs(value=value, ref_identities=ref_identities)
            if key == CURSOR_INPUTS_CONFIG_KEY
            else value
            for key, value in config.items()
            if key not in MIGRATION_FINGERPRINT_EXCLUDED_CONFIG_KEYS
        }
    return identity


def _resolved_cursor_inputs(*, value: Any, ref_identities: Mapping[str, str]) -> Any:
    if not isinstance(value, dict):
        return value
    return {ref_identities.get(str(name), str(name)): column for name, column in value.items()}


def _normalized_query_sql(
    *, query_sql: str, ref_identities: Mapping[str, str], dialect: str | None
) -> str | None:
    placeholder_sql: str = _REF_MARKER.sub(
        lambda match: _ref_placeholder(
            identity=ref_identities.get(
                match.group(1) or match.group(2), match.group(1) or match.group(2)
            )
        ),
        query_sql,
    )
    polyglot: Any = import_polyglot_sql()
    effective_dialect: str = dialect or _GENERIC_DIALECT
    try:
        parsed: dict[str, Any] = polyglot.parse_one(
            placeholder_sql, dialect=effective_dialect
        ).to_dict()
    except polyglot.PolyglotError:
        return None
    stripped: Any = _strip_formatting(parsed)
    definitions: list[tuple[str, bool]] = _local_names(stripped)
    ordered_names: list[str] = list(dict.fromkeys(name for name, _ in definitions))
    local_names: dict[str, str] = {
        name: f"{MIGRATION_LOCAL_NAME_PREFIX}{index}"
        for index, name in enumerate(ordered_names, start=1)
    }
    cte_names: dict[str, str] = {name: local_names[name] for name, is_cte in definitions if is_cte}
    canonical: Any = _canonical_local_names(node=stripped, names=local_names, cte_names=cte_names)
    generated: list[str] = polyglot.generate(canonical, dialect=effective_dialect)
    return "\n".join(generated)


def _ref_placeholder(*, identity: str) -> str:
    digest: str = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"{MIGRATION_REF_PLACEHOLDER_PREFIX}{digest}"


def _strip_formatting(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: [] if key.endswith(_COMMENTS_SUFFIX) else _strip_formatting(value)
            for key, value in node.items()
            if key != _SPAN_KEY
        }
    if isinstance(node, list):
        return [_strip_formatting(value) for value in node]
    return node


def _local_names(node: Any) -> list[tuple[str, bool]]:
    """Return (name, is_cte) for CTE and relation alias definitions in first-seen order."""

    found: list[tuple[str, bool]] = []
    if isinstance(node, list):
        item: Any
        for item in node:
            found.extend(_local_names(item))
        return found
    if not isinstance(node, dict):
        return found
    with_clause: Any = node.get(_WITH_KEY)
    if isinstance(with_clause, dict):
        cte_aliases: list[Any] = [
            cte.get(_ALIAS_KEY) for cte in with_clause.get(_CTES_KEY) or () if isinstance(cte, dict)
        ]
        found.extend((name, True) for name in _identifier_names(cte_aliases))
    key: str
    value: Any
    for key, value in node.items():
        if key in _ALIASED_RELATION_KEYS and _is_relation(value):
            found.extend((name, False) for name in _identifier_names([value.get(_ALIAS_KEY)]))
        found.extend(_local_names(value))
    return found


def _identifier_names(identifiers: list[Any]) -> list[str]:
    return [
        str(identifier[_IDENTIFIER_NAME_KEY]).lower()
        for identifier in identifiers
        if _is_identifier(identifier)
    ]


def _canonical_local_names(
    *, node: Any, names: Mapping[str, str], cte_names: Mapping[str, str]
) -> Any:
    """Rename CTE and alias names only where they define or qualify a relation."""

    if isinstance(node, list):
        return [
            _canonical_local_names(node=value, names=names, cte_names=cte_names) for value in node
        ]
    if not isinstance(node, dict):
        return node
    rewritten: dict[str, Any] = {
        key: _canonical_local_names(node=value, names=names, cte_names=cte_names)
        for key, value in node.items()
    }
    key: str
    value: Any
    for key, value in node.items():
        if key in _QUALIFIED_REFERENCE_KEYS and isinstance(value, dict):
            rewritten[key] = {
                **rewritten[key],
                _TABLE_KEY: _renamed(identifier=value.get(_TABLE_KEY), names=names),
            }
        elif key in _ALIASED_RELATION_KEYS and _is_relation(value):
            rewritten[key] = {
                **rewritten[key],
                _ALIAS_KEY: _renamed(identifier=value.get(_ALIAS_KEY), names=names),
                **_cte_reference(relation=value, cte_names=cte_names),
            }
        elif key == _WITH_KEY and isinstance(value, dict):
            rewritten[key] = {
                **rewritten[key],
                _CTES_KEY: [
                    {**cte, _ALIAS_KEY: _renamed(identifier=cte.get(_ALIAS_KEY), names=names)}
                    for cte in rewritten[key].get(_CTES_KEY) or ()
                ],
            }
    return rewritten


def _cte_reference(*, relation: dict[str, Any], cte_names: Mapping[str, str]) -> dict[str, Any]:
    """Rename an unqualified relation name that refers to a CTE."""

    qualifiers: tuple[Any, ...] = tuple(relation.get(key) for key in _RELATION_QUALIFIER_KEYS)
    name: Any = relation.get(_IDENTIFIER_NAME_KEY)
    if any(qualifier is not None for qualifier in qualifiers) or not _is_identifier(name):
        return {}
    return {_IDENTIFIER_NAME_KEY: _renamed(identifier=name, names=cte_names)}


def _renamed(*, identifier: Any, names: Mapping[str, str]) -> Any:
    if not _is_identifier(identifier):
        return identifier
    canonical: str | None = names.get(str(identifier[_IDENTIFIER_NAME_KEY]).lower())
    if canonical is None:
        return identifier
    return {**identifier, _IDENTIFIER_NAME_KEY: canonical, _IDENTIFIER_QUOTED_KEY: False}


def _is_relation(node: Any) -> bool:
    return isinstance(node, dict) and not _is_identifier(node)


def _is_identifier(node: Any) -> bool:
    return (
        isinstance(node, dict)
        and isinstance(node.get(_IDENTIFIER_NAME_KEY), str)
        and _IDENTIFIER_QUOTED_KEY in node
    )


def with_migration_fingerprints(
    *,
    entries: tuple[ModelPlanEntry, ...],
    models_by_name: Mapping[str, CompiledModel],
    dialect: str | None,
) -> tuple[ModelPlanEntry, ...]:
    """Attach the current-name migration fingerprint each build stores with its fingerprint."""

    attached: list[ModelPlanEntry] = []
    entry: ModelPlanEntry
    for entry in entries:
        model: CompiledModel | None = models_by_name.get(entry.name)
        if model is None or entry.fingerprint_metadata_json is None:
            attached.append(entry)
            continue
        attached.append(
            replace(
                entry,
                migration_fingerprint=build_migration_fingerprint(
                    query_sql=model.query_sql,
                    metadata_json=entry.fingerprint_metadata_json,
                    ref_identities={},
                    dialect=dialect,
                ),
            )
        )
    return tuple(attached)
