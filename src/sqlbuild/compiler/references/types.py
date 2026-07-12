"""SQL reference type-layer declarations."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol


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


class ExternalSqlReferenceResolver(Protocol):
    """Resolve first-class SQLBuild references backed by external metadata."""

    def validate_model_names(self, *, known_model_names: set[str]) -> None:
        """Validate SQLBuild model names against external integration resources."""

    def extend_sql_test_model_names(self, *, known_model_names: set[str]) -> set[str]:
        """Return extra model names valid for SQL-native test targets."""

    def extend_sql_test_source_names(self, *, known_source_names: set[str]) -> set[str]:
        """Return extra source names valid for SQL-native test mocks."""

    def extend_sql_test_seed_names(self, *, known_seed_names: set[str]) -> set[str]:
        """Return extra seed names valid for SQL-native test mocks."""

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
