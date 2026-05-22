"""Shared type-layer declarations."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal, NotRequired, Protocol, TypedDict


class LoaderColumnSpec(TypedDict):
    """Column declaration accepted by the public loader decorator."""

    name: str
    type: NotRequired[str]
    nullable: NotRequired[bool]
    description: NotRequired[str]
    meta: NotRequired[dict[str, object]]


class SqlReferenceKind(StrEnum):
    REF = "ref"
    SEED = "seed"
    SOURCE = "source"
    DBT_REF = "dbt_ref"
    UDF = "udf"
    TABLE_FUNCTION = "table_fn"

    @property
    def function_name(self) -> str:
        return f"__{self.value}"

    @property
    def fixture_cte_prefix(self) -> str:
        return f"{self.function_name}__"

    def example_call(self, *args: str, quote: Literal["'", '"'] = "'") -> str:
        quoted_args: str = ", ".join(
            f"{quote}{arg.replace(quote, quote + quote)}{quote}" for arg in args
        )
        return f"{self.function_name}({quoted_args})"

    def placeholder_call(self, placeholder: str = "") -> str:
        return f"{self.function_name}({placeholder})"


class ExecutionResourceKind(StrEnum):
    """Top-level resource kind displayed during execution."""

    SOURCE = "source"
    LOADER = "loader"
    SEED = "seed"
    FUNCTION = "function"
    VIEW = "view"
    TABLE = "table"
    CUSTOM = "custom"
    SNAPSHOT = "snapshot"


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
