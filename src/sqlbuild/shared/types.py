"""Shared type-layer declarations."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ExternalSqlReferenceResolver(Protocol):
    """Resolve first-class SQLBuild references backed by external metadata.

    Core compiler and planner code owns parsing and dependency semantics for
    supported syntax such as ``__dbt_ref(...)``. Provider integrations own the
    metadata needed to resolve those references, such as DBT manifest loading and
    model lookup, and expose that behavior through this protocol.
    """

    def validate_model_names(self, *, known_model_names: set[str]) -> None:
        """Validate SQLBuild model names against external integration resources."""

    def validate_reference(
        self,
        *,
        ref_kind: str,
        ref_name: str,
        ref_package: str | None,
        owner_relative_sql_path: Path,
    ) -> None:
        """Validate one external SQL reference from a SQLBuild-owned file."""

    def resolve_reference(
        self,
        *,
        ref_kind: str,
        ref_name: str,
        ref_package: str | None,
    ) -> str | None:
        """Return the physical relation for an external reference, if resolvable."""
