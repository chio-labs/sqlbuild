"""Strict adapter requiring full implementation of every method."""

from __future__ import annotations

from abc import abstractmethod
from decimal import Decimal
from typing import Any

from sqlbuild.adapter.shared.classes.connection import ConnectionMixin
from sqlbuild.adapter.shared.classes.diff import DiffMixin
from sqlbuild.adapter.shared.classes.materialization import MaterializationMixin
from sqlbuild.adapter.shared.classes.schema import SchemaMixin
from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    CursorValue,
    ExpressionInferenceProfile,
    RowDiffTolerance,
    RowDiffTolerances,
    StatementRecorder,
)
from sqlbuild.adapter.shared.types import FrameworkType, PromotionStrategy, TablePromotionMode
from sqlbuild.compiler.compile.types import FunctionLanguage


class StrictAdapter(
    ConnectionMixin,
    SchemaMixin,
    MaterializationMixin,
    DiffMixin,
):
    """All-abstract adapter interface.

    Subclass this to be forced to implement every adapter method explicitly.
    The concrete defaults from ConnectionMixin (begin, commit, rollback,
    transaction, supports_transactions) are inherited but may be overridden.
    """

    @abstractmethod
    def supports_zero_copy_clone(self) -> bool:
        """Return whether clone operations can use zero-copy semantics."""
        ...

    @abstractmethod
    def supports_relation_age_metadata(self) -> bool:
        """Return whether relation metadata includes reliable age information."""
        ...

    @abstractmethod
    def supports_python_functions(self) -> bool:
        """Return whether the adapter can create Python UDF resources."""
        ...

    @abstractmethod
    def persists_python_functions(self) -> bool:
        """Return whether Python UDF resources survive across connections."""
        ...

    @abstractmethod
    def python_functions_inherit_default_namespace(self) -> bool:
        """Return whether Python UDFs inherit default database/schema targets."""
        ...

    @abstractmethod
    def supports_unqualified_function_fingerprints(self) -> bool:
        """Return whether unqualified functions can store fingerprints elsewhere."""
        ...

    @abstractmethod
    def supports_table_functions(self) -> bool:
        """Return whether the adapter can create table function resources."""
        ...

    @abstractmethod
    def recommended_max_sql_length(self) -> int | None:
        """Return the recommended maximum SQL length for lightweight queries."""
        ...

    @abstractmethod
    def describe_relation(self, connection: Any, relation: str) -> tuple[ColumnInfo, ...]:
        """Return relation column metadata."""
        ...

    @abstractmethod
    def query_column_names(self, connection: Any, sql: str) -> tuple[str, ...]:
        """Return column names produced by a SQL query."""
        ...

    @abstractmethod
    def build_cursor_filter(
        self,
        *,
        cursor_column: str | None,
        start_cursor: CursorValue | None,
        end_cursor: CursorValue | None,
    ) -> str:
        """Build a WHERE clause fragment for cursor-bounded queries."""
        ...

    @abstractmethod
    def schema_exists(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str,
    ) -> bool:
        """Return whether the named schema exists in the warehouse."""
        ...

    @abstractmethod
    def render_create_schema(
        self,
        *,
        database: str | None,
        schema: str,
    ) -> tuple[str, ...]:
        """Render SQL statements that create a schema if missing."""
        ...

    @abstractmethod
    def render_create_table_as(self, *, target: str, sql: str) -> tuple[str, ...]:
        """Render SQL statements that create or replace a table from a query."""
        ...

    @abstractmethod
    def render_create_view_as(self, *, target: str, sql: str) -> tuple[str, ...]:
        """Render SQL statements that create or replace a view from a query."""
        ...

    @abstractmethod
    def render_table_function_call(self, *, target: str, arguments_sql: str) -> str:
        """Render a table function call for use as a FROM target."""
        ...

    @abstractmethod
    def render_create_function(
        self,
        *,
        target: str,
        arguments: tuple[Any, ...],
        returns: str,
        body_sql: str,
        return_columns: tuple[Any, ...] = (),
        language: FunctionLanguage = FunctionLanguage.SQL,
        runtime_version: str | None = None,
        entry_point: str | None = None,
        packages: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        """Render SQL statements that create or replace a SQL function."""
        ...

    @abstractmethod
    def render_append(
        self, *, target: str, sql: str, columns: tuple[str, ...] | None = None
    ) -> tuple[str, ...]:
        """Render SQL statements that insert query rows into a target."""
        ...

    @abstractmethod
    def render_delete_insert(
        self,
        *,
        target: str,
        sql: str,
        unique_key: tuple[str, ...],
        columns: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        """Render SQL statements for delete-insert by unique key."""
        ...

    @abstractmethod
    def render_delete_insert_cursor(
        self,
        *,
        target: str,
        sql: str,
        cursor_column: str,
        cursor_start: str,
        cursor_end: str,
        columns: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        """Render SQL statements for cursor-bounded delete-insert."""
        ...

    @abstractmethod
    def render_drop(self, *, target: str, if_exists: bool = True) -> tuple[str, ...]:
        """Render SQL statements that drop a relation."""
        ...

    @abstractmethod
    def render_drop_view(self, *, target: str, if_exists: bool = True) -> tuple[str, ...]:
        """Render SQL statements that drop a view relation."""
        ...

    @abstractmethod
    def drop_view(
        self,
        connection: Any,
        *,
        target: str,
        if_exists: bool = True,
        statement_recorder: StatementRecorder,
    ) -> None:
        """Drop a view relation."""
        ...

    @abstractmethod
    def render_rename(self, *, source: str, target: str) -> tuple[str, ...]:
        """Render SQL statements that rename a relation."""
        ...

    @abstractmethod
    def render_swap(self, *, left: str, right: str) -> tuple[str, ...]:
        """Render SQL statements that swap two relations."""
        ...

    @abstractmethod
    def render_clone(
        self,
        *,
        source: str,
        target: str,
        hard_copy: bool = False,
    ) -> tuple[str, ...]:
        """Render SQL statements that clone or copy a relation."""
        ...

    @abstractmethod
    def render_replace_table_from_relation(self, *, target: str, source: str) -> tuple[str, ...]:
        """Render SQL statements that replace a target table from a source relation."""
        ...

    @abstractmethod
    def replace_table_from_relation(
        self,
        connection: Any,
        *,
        target: str,
        source: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        """Replace a target table from a source relation."""
        ...

    @abstractmethod
    def render_add_columns(
        self, *, target: str, columns: tuple[ColumnInfo, ...]
    ) -> tuple[str, ...]:
        """Render SQL statements that add columns to a table."""
        ...

    @abstractmethod
    def render_drop_columns(self, *, target: str, column_names: tuple[str, ...]) -> tuple[str, ...]:
        """Render SQL statements that drop columns from a table."""
        ...

    @abstractmethod
    def render_alter_column_types(
        self, *, target: str, columns: tuple[ColumnInfo, ...]
    ) -> tuple[str, ...]:
        """Render SQL statements that alter column types on a table."""
        ...

    @abstractmethod
    def render_merge(
        self,
        *,
        target: str,
        sql: str,
        unique_key: tuple[str, ...],
        source_columns: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        """Render SQL statements that merge query rows into a target."""
        ...

    @abstractmethod
    def validate_row_diff_keys(
        self,
        connection: Any,
        *,
        relation_sql: str,
        relation_label: str,
        keys: tuple[str, ...],
    ) -> None:
        """Validate row-diff unique keys for nulls and duplicates."""
        ...

    @abstractmethod
    def build_row_diff_equal_expression(
        self,
        *,
        column: str,
        column_info: ColumnInfo,
        tolerances: RowDiffTolerances | None,
    ) -> str:
        """Build a boolean equality expression for one row-diff column."""
        ...

    @abstractmethod
    def resolve_row_diff_tolerance(
        self,
        *,
        column: str,
        column_type: str,
        tolerances: RowDiffTolerances | None,
    ) -> RowDiffTolerance | None:
        """Resolve applicable row-diff tolerance for a column."""
        ...

    @abstractmethod
    def validate_row_diff_tolerance(self, *, column: str, tolerance: RowDiffTolerance) -> None:
        """Validate one row-diff tolerance definition."""
        ...

    @abstractmethod
    def normalize_row_diff_numeric_type(self, column_type: str) -> str | None:
        """Normalize one column type into a row-diff numeric family."""
        ...

    @abstractmethod
    def format_row_diff_decimal_sql(self, value: Decimal) -> str:
        """Format a decimal value for row-diff SQL."""
        ...

    @abstractmethod
    def default_schema(self) -> str | None:
        """Return the adapter's default schema name, or None if schema is required."""
        ...

    @abstractmethod
    def default_database(self) -> str | None:
        """Return the adapter's default database name, or None if database is required."""
        ...

    @abstractmethod
    def star_exclude_keyword(self) -> str:
        """Return the SQL keyword for SELECT * EXCLUDE/EXCEPT syntax."""
        ...

    @abstractmethod
    def render_qualified_name(
        self,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> str | None:
        """Render a fully qualified relation name for this adapter."""
        ...

    @abstractmethod
    def render_framework_type(self, type_name: FrameworkType) -> str:
        """Render one framework-internal logical type for this adapter."""
        ...

    @abstractmethod
    def render_set_difference_operator(self) -> str:
        """Render the set-difference operator keyword for this adapter."""
        ...

    @abstractmethod
    def sqlglot_dialect(self) -> str | None:
        """Return the SQLGlot dialect name for this adapter, if any."""
        ...

    @abstractmethod
    def expression_inference_profile(self) -> ExpressionInferenceProfile:
        """Return static SQL expression inference behavior for this adapter."""
        ...

    @abstractmethod
    def render_cursor_bound_literal(self, value: str, cursor_type: str | None) -> str:
        """Render one cursor bound literal for this adapter and cursor type."""
        ...

    @abstractmethod
    def default_table_promotion_mode(self) -> TablePromotionMode:
        """Return the adapter default table promotion mode."""
        ...

    @abstractmethod
    def default_promotion_strategy(self) -> PromotionStrategy:
        """Return the adapter default staged table promotion strategy."""
        ...
