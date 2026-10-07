"""Shared values and helpers for compiler frontier tests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from sqlbuild.compiler.compile.models import CompactLineageFacts
from sqlbuild.compiler.fact_cache.main._compile_cache_root import compile_cache_root
from sqlbuild.compiler.frontier.main.compiler_cache_directory import compiler_cache_directory
from sqlbuild.compiler.scopes.constants import SCOPE_CACHE_DIRECTORY_NAME
from sqlbuild.compiler.sql_analysis.classes.binding_catalog import BindingCatalog
from sqlbuild.rule_engine._helpers.run.cache_paths import rules_bulk_cache_path

HELPERS_MODULE: str = "tests.unit.src.sqlbuild.compiler.frontier.helpers"


class OrderStatus(StrEnum):
    """A neutral enum captured by name."""

    PLACED = "placed"


@dataclass(frozen=True)
class OrderLine:
    """A neutral dataclass captured field by field."""

    order_id: int
    status: OrderStatus
    path: PurePosixPath


def order_total(amount_cents: int) -> int:
    """A neutral callable captured by its qualified name."""

    return amount_cents


class LinkedCustomer:
    """A plain object that can point back at itself."""

    def __init__(self) -> None:
        self.name: str = "customer"
        self.peer: LinkedCustomer | None = None


def linked_customer() -> LinkedCustomer:
    """Return a customer whose peer is itself."""

    customer: LinkedCustomer = LinkedCustomer()
    customer.peer = customer
    return customer


class MemoCatalog:
    """A plain object with one memo map and one ordered map."""

    def __init__(self, *, memo: dict[str, int], ordered: dict[str, int]) -> None:
        self.memo: dict[str, int] = memo
        self.ordered: dict[str, int] = ordered


def memo_catalog(*, memo_keys: tuple[str, ...], ordered_keys: tuple[str, ...]) -> MemoCatalog:
    """Return a catalog whose maps were filled in the given key orders."""

    return MemoCatalog(
        memo={key: len(key) for key in memo_keys},
        ordered={key: len(key) for key in ordered_keys},
    )


def orders_lineage(*, string_pool: tuple[str, ...], source_index: int) -> CompactLineageFacts:
    """Return `order_id` read directly from a source, indexed into a batch-wide string pool."""

    position: dict[str, int] = {value: index for index, value in enumerate(string_pool)}
    return CompactLineageFacts(
        string_pool=string_pool,
        rows=(
            (
                position["order_id"],
                0,
                1,
                ((position["source"], source_index, position["order_id"]),),
            ),
        ),
    )


def orders_binding_catalog(
    *, shared_analyses: tuple[tuple[str, str], ...], relations: tuple[str, ...]
) -> BindingCatalog:
    """Return a catalog whose memo and relation map were filled in the given orders."""

    catalog: BindingCatalog = BindingCatalog(
        dialect="duckdb",
        quoted_ignore_case=False,
        known_functions=(),
        known_types=(),
        relations={name: {"order_id": "INTEGER"} for name in relations},
    )
    catalog.shared_analyses.update(shared_analyses)
    return catalog


def order_line() -> OrderLine:
    """Return one neutral order line."""

    return OrderLine(order_id=7, status=OrderStatus.PLACED, path=PurePosixPath("models/a.sql"))


def store_paths(project_dir: Path) -> tuple[str, ...]:
    """Return every engine-owned store path relative to the project directory."""

    paths: tuple[Path, ...] = (
        compiler_cache_directory(project_dir),
        compile_cache_root(project_dir=project_dir, target_config=None, no_cache=False)
        or project_dir,
        compiler_cache_directory(project_dir) / SCOPE_CACHE_DIRECTORY_NAME,
        rules_bulk_cache_path(project_dir=project_dir, file_name="sql.json"),
    )
    return tuple(path.relative_to(project_dir).as_posix() for path in paths)
