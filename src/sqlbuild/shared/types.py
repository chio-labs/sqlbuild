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


class PythonNodeColumnSpec(TypedDict):
    """Column declaration accepted by dataset-like Python node decorators."""

    name: str
    type: NotRequired[str]
    nullable: NotRequired[bool]
    description: NotRequired[str]
    meta: NotRequired[dict[str, object]]


class ColumnLineageRefSpec(TypedDict):
    """Graph-based upstream column reference accepted by Python node decorators."""

    node: str
    column: str


class PythonCheckSeverity(StrEnum):
    """Severity for Python check results."""

    ERROR = "error"
    WARN = "warn"


class SqlResourceRefKind(StrEnum):
    """Python-node typed dependency target for SQL graph resources."""

    MODEL = "model"
    SOURCE = "source"


class LocalNodePlanAction(StrEnum):
    """Neutral action for one locally classified graph node."""

    RUN = "run"
    CURRENT = "current"


class LocalNodePlanReason(StrEnum):
    """Neutral reason for one locally classified graph node."""

    FIRST_RUN = "first_run"
    FULL_REFRESH = "full_refresh"
    RELATION_MISSING = "relation_missing"
    LOCAL_CHANGED = "local_changed"
    NO_CHANGE = "no_change"


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
    UDF = "udf"
    TABLE_FN = "table_fn"
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
