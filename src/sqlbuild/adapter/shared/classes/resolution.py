"""Naming resolution mixin for adapter implementations."""

from __future__ import annotations

from abc import abstractmethod


class ResolutionMixin:
    """Resolves logical relation names to physical warehouse identifiers."""

    @abstractmethod
    def resolve_database(
        self,
        *,
        model_database: str | None,
        environment: str | None,
        vars: dict[str, str],
    ) -> str | None:
        """Return the physical database name for a declared logical database."""
        ...

    @abstractmethod
    def resolve_schema(
        self,
        *,
        model_schema: str | None,
        environment: str | None,
        vars: dict[str, str],
    ) -> str | None:
        """Return the physical schema name for a declared logical schema."""
        ...
