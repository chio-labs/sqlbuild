"""Shared type-layer declarations."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ExternalReferenceResolver(Protocol):
    """Resolve and validate references owned by optional external integrations."""

    def validate_model_names(self, *, known_model_names: set[str]) -> None:
        """Validate SQLBuild model names against external integration resources."""

    def validate_reference(
        self,
        *,
        ref_kind: str,
        ref_name: str,
        ref_package: str | None,
        owner_relative_path: Path,
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
