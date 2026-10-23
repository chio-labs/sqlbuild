"""Helpers for review schema lifecycle tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

DROP_PREFIX: str = "DROP SCHEMA IF EXISTS "
DROP_SUFFIX: str = " CASCADE"


class FoldingWarehouseAdapter:
    """Stores unquoted schema names folded as a warehouse does, and checks them as its adapter does.

    Postgres and Databricks store unquoted names in lowercase and compare `schema_name` exactly;
    Snowflake stores them in uppercase and compares `UPPER(schema_name)` with `UPPER(name)`.
    """

    def __init__(
        self,
        *,
        fold: Callable[[str], str],
        compare: Callable[[str], str],
        schemas: tuple[str, ...] = (),
    ) -> None:
        self.fold: Callable[[str], str] = fold
        self.compare: Callable[[str], str] = compare
        self.schemas: set[str] = {fold(schema) for schema in schemas}

    def schema_exists(self, *, connection: Any, database: str | None, schema: str) -> bool:
        del connection, database
        return any(self.compare(stored) == self.compare(schema) for stored in self.schemas)

    def render_drop_schema(self, *, database: str | None, schema: str) -> tuple[str, ...]:
        del database
        return (f"{DROP_PREFIX}{schema}{DROP_SUFFIX}",)

    def execute(self, *, connection: Any, sql: str) -> None:
        del connection
        unquoted: str = sql.removeprefix(DROP_PREFIX).removesuffix(DROP_SUFFIX)
        self.schemas.discard(self.fold(unquoted))
