"""dbt manifest lookup models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DbtManifestModel:
    """One dbt model node needed for SQLBuild dbt_ref resolution."""

    unique_id: str
    package_name: str
    name: str
    relation_name: str
    database: str | None = None
    schema: str | None = None
    alias: str | None = None
    depends_on_nodes: tuple[str, ...] = field(default_factory=tuple)
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DbtManifestIndex:
    """Lookup indexes for dbt model nodes in a manifest."""

    models_by_unique_id: dict[str, DbtManifestModel]
    models_by_name: dict[str, tuple[DbtManifestModel, ...]]
    models_by_package_and_name: dict[tuple[str, str], DbtManifestModel]
