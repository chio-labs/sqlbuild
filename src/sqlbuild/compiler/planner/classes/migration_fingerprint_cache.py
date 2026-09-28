"""Migration fingerprints computed at most once per model definition in one plan."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.planner._helpers.migrations.fingerprint import (
    build_migration_fingerprint,
    migration_fingerprint_ref_names,
)

type _FingerprintKey = tuple[str, str, str | None, tuple[tuple[str, str], ...]]


class MigrationFingerprintCache:
    """Reuse migration fingerprints across rename-map variants and planning phases."""

    def __init__(self) -> None:
        self._ref_names: dict[tuple[str, str], frozenset[str]] = {}
        self._fingerprints: dict[_FingerprintKey, str | None] = {}

    def fingerprint(
        self,
        *,
        query_sql: str,
        metadata_json: str,
        ref_identities: Mapping[str, str],
        dialect: str | None,
    ) -> str | None:
        """Return the migration fingerprint, keyed only by the renames this model can see."""

        definition: tuple[str, str] = (query_sql, metadata_json)
        names: frozenset[str] | None = self._ref_names.get(definition)
        if names is None:
            names = migration_fingerprint_ref_names(
                query_sql=query_sql, metadata_json=metadata_json
            )
            self._ref_names[definition] = names
        visible: dict[str, str] = {
            name: ref_identities[name] for name in sorted(names) if name in ref_identities
        }
        key: _FingerprintKey = (query_sql, metadata_json, dialect, tuple(visible.items()))
        if key not in self._fingerprints:
            self._fingerprints[key] = build_migration_fingerprint(
                query_sql=query_sql,
                metadata_json=metadata_json,
                ref_identities=visible,
                dialect=dialect,
            )
        return self._fingerprints[key]
