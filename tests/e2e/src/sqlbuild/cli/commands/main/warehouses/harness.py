"""Per-warehouse hooks that let one scenario module run against every real warehouse."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pytest

Rows = tuple[tuple[object, ...], ...]


def _identity(text: str) -> str:
    return text


def _cast_date(expression: str) -> str:
    return f"CAST({expression} AS DATE)"


def _is_null(expression: str) -> str:
    return f"{expression} IS NULL"


def _no_timing(label: str) -> AbstractContextManager[None]:
    del label
    return nullcontext()


def _no_local_files(schema_name: str) -> dict[str, str]:
    del schema_name
    return {}


def _no_leftovers(schema_name: str) -> Rows:
    del schema_name
    return ()


def _no_loader_fixture(tmp_path: Path) -> tuple[Path, str]:
    raise NotImplementedError(f"the source loader strategy fixture is not wired at {tmp_path}")


def _no_source_deferral(project_name: str, dev_schema: str, prod_schema: str) -> str:
    raise NotImplementedError(f"source deferral is not wired for {project_name}")


def _no_scenario_relations(schema_name: str) -> tuple[str, ...]:
    raise NotImplementedError(f"scenario relation listing is not wired for {schema_name}")


def _schema_location(schema_name: str) -> str:
    return f"    schema: {schema_name}\n"


def _default_dlt_schemas(schema_base: str) -> tuple[str, str]:
    return f"{schema_base}_models", f"{schema_base}_raw"


@dataclass(frozen=True)
class WarehouseHarness:
    """The warehouse-specific operations a shared real-warehouse scenario needs.

    Every schema-scoped callable takes the schema (BigQuery dataset) name first.
    """

    name: str
    unique_schema: Callable[[str], str]
    project_toml: Callable[[str, str], str]
    ensure_schema: Callable[[str], None]
    cleanup_schema: Callable[[str], None]
    fetch_rows: Callable[[str, str], Rows]
    execute_sql: Callable[[str, str], None]
    relation: Callable[[str, str], str]
    prepare_source_loader_strategies: Callable[[Path], tuple[Path, str]] = _no_loader_fixture
    source_deferral_project_toml: Callable[[str, str, str], str] = _no_source_deferral
    adapt_sql: Callable[[str], str] = _identity
    date_sql: Callable[[str], str] = _cast_date
    null_flag_sql: Callable[[str], str] = _is_null
    true_text: str = "True"
    false_text: str = "False"
    text_type: str = "VARCHAR"
    deferral_text_type: str = "VARCHAR"
    seeds_with_ctas: bool = False
    timing: Callable[[str], AbstractContextManager[None]] = _no_timing
    local_files: Callable[[str], dict[str, str]] = _no_local_files
    snapshot_leftovers: Callable[[str], Rows] = _no_leftovers
    dlt_schemas: Callable[[str], tuple[str, str]] = _default_dlt_schemas
    scenario_relation_names: Callable[[str], tuple[str, ...]] = _no_scenario_relations
    source_location_yaml: Callable[[str], str] = _schema_location
    precreate_schema: bool = True

    def precreate(self, schema_name: str) -> None:
        """Create the schema up front unless this scenario relies on SQLBuild creating it."""

        if self.precreate_schema:
            self.ensure_schema(schema_name)

    def seed_statements(
        self, relation: str, columns: str, values: str, select: str
    ) -> tuple[str, ...]:
        """Create and fill one table, by CTAS where the warehouse suite always seeded that way."""

        return {
            True: (f"CREATE OR REPLACE TABLE {relation} AS {select}",),
            False: (
                f"CREATE TABLE {relation} ({columns})",
                f"INSERT INTO {relation} VALUES {values}",
            ),
        }[self.seeds_with_ctas]

    def row_count(self, schema_name: str, name: str) -> int:
        rows: Rows = self.fetch_rows(
            schema_name, f"SELECT COUNT(*) FROM {self.relation(schema_name, name)}"
        )
        return int(str(rows[0][0]))

    def flag(self, value: bool) -> str:
        return {True: self.true_text, False: self.false_text}[value]


@dataclass(frozen=True)
class WarehouseSetup:
    """One warehouse a scenario runs on, and whether the test precreates its schema."""

    name: str
    source_location_yaml: Callable[[str], str] = _schema_location
    precreate_schema: bool = True


WAREHOUSE_MARKS: dict[str, tuple[pytest.MarkDecorator, ...]] = {
    name: (pytest.mark.real_warehouse, getattr(pytest.mark, name))
    for name in ("bigquery", "snowflake", "databricks", "postgres", "sqlserver", "clickhouse")
}


def on_warehouses(*setups: WarehouseSetup | str) -> list[object]:
    """Parametrize the indirect ``warehouse`` fixture with each warehouse's markers."""

    resolved: tuple[WarehouseSetup, ...] = tuple(
        setup if isinstance(setup, WarehouseSetup) else WarehouseSetup(name=setup)
        for setup in setups
    )
    return [
        pytest.param(setup, marks=WAREHOUSE_MARKS[setup.name], id=setup.name) for setup in resolved
    ]


class DescribedCase(Protocol):
    @property
    def description(self) -> str: ...


def on_warehouse_cases(cases: Mapping[str, tuple[DescribedCase, ...]]) -> list[object]:
    """Parametrize ``warehouse`` and ``test_case`` with cases that differ per warehouse."""

    return [
        pytest.param(
            WarehouseSetup(name=name),
            case,
            marks=WAREHOUSE_MARKS[name],
            id=f"{name}-{case.description}",
        )
        for name, warehouse_cases in cases.items()
        for case in warehouse_cases
    ]
