"""Helpers for warehouse snapshot planner tests."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject, CompiledSource
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredSourceFile
from sqlbuild.compiler.planner._helpers.warehouse.snapshot import (
    _CursorModelInfo,
    _PhysicalCursorQuery,
)
from sqlbuild.compiler.planner._helpers.warehouse.source_tables import (
    check_selected_source_tables_exist,
)
from sqlbuild.compiler.planner.models import PlannerRelationsContext, PlannerScope
from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.spec.contracts.models import SourceEntry, StartCursorsConfig


class CursorBoundRows:
    """Fetchable result of one cursor-bound statement double."""

    def __init__(self, rows: list[tuple[str | None, ...]]) -> None:
        self._rows: list[tuple[str | None, ...]] = rows

    def fetchall(self) -> list[tuple[str | None, ...]]:
        return self._rows


def _answer_cursor_relation(relation: str) -> CursorBoundRows:
    day: int = int(relation.rsplit("_", 1)[1]) % 28 + 1
    return CursorBoundRows([(f"2026-01-{day:02d}", f"2026-02-{day:02d}")])


def _reject_cursor_relation(relation: str) -> CursorBoundRows:
    raise RuntimeError(f"Object '{relation}' does not exist or not authorized.")


_CURSOR_RELATION_ANSWERS: dict[bool, Callable[[str], CursorBoundRows]] = {
    False: _answer_cursor_relation,
    True: _reject_cursor_relation,
}


class ConcurrencyTrackingCursorExecute:
    """Execute double answering one MIN/MAX statement per relation while counting overlap."""

    def __init__(self, *, failing_relations: frozenset[str], latency_seconds: float) -> None:
        self._failing_relations: frozenset[str] = failing_relations
        self._latency_seconds: float = latency_seconds
        self._lock: threading.Lock = threading.Lock()
        self._active: int = 0
        self.max_active: int = 0
        self.sql: list[str] = []

    def __call__(self, *, connection: Any, sql: str) -> CursorBoundRows:
        del connection
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
            self.sql.append(sql)
        try:
            time.sleep(self._latency_seconds)
            relation: str = sql.rsplit(" FROM ", 1)[1]
            return _CURSOR_RELATION_ANSWERS[relation in self._failing_relations](relation)
        finally:
            with self._lock:
                self._active -= 1


def build_cursor_bound_queries(count: int) -> list[_PhysicalCursorQuery]:
    """Return one MIN/MAX physical cursor query per synthetic orders relation."""

    return [
        _PhysicalCursorQuery(
            relation=f"analytics.raw.orders_{index}",
            cursor_column="ordered_at",
            min_tags=(f"model_{index}__orders__min",),
            max_tags=(f"model_{index}__orders__max",),
        )
        for index in range(count)
    ]


class EligibleMaxAdapter:
    """Adapter double rendering bounded MAX statements and allowing parallel reads."""

    metadata_inspection_concurrency: int = 4

    def render_max_cursor_at_or_before(
        self,
        *,
        relation: str,
        cursor_column: str,
        maximum_allowed: str,
        cursor_type: str,
        is_date: bool,
    ) -> str:
        del cursor_type, is_date
        return (
            f"SELECT CAST(MAX({cursor_column}) AS VARCHAR) FROM {relation} "
            f"WHERE {cursor_column} <= '{maximum_allowed}'"
        )


def _answer_eligible_max(relation: str) -> CursorBoundRows:
    del relation
    return CursorBoundRows([("2026-01-15",)])


_ELIGIBLE_MAX_ANSWERS: dict[bool, Callable[[str], CursorBoundRows]] = {
    False: _answer_eligible_max,
    True: _reject_cursor_relation,
}


class EligibleMaxExecute:
    """Execute double failing the bounded MAX read of one relation."""

    def __init__(self, *, failing_relation: str, latency_seconds: float) -> None:
        self._failing_relation: str = failing_relation
        self._latency_seconds: float = latency_seconds

    def __call__(self, *, connection: Any, sql: str) -> CursorBoundRows:
        del connection
        time.sleep(self._latency_seconds)
        relation: str = sql.split(" FROM ", 1)[1].split(" ", 1)[0]
        return _ELIGIBLE_MAX_ANSWERS[relation == self._failing_relation](relation)


def build_eligible_max_cursor_models(count: int) -> list[_CursorModelInfo]:
    """Return timestamp cursor models whose target MAX is beyond a one-day horizon."""

    return [
        _CursorModelInfo(
            model_name=f"model_{index}",
            target_tag=f"model_{index}__target__max",
            target_relation=f"analytics.marts.orders_{index}",
            cursor_column="ordered_at",
            upstreams=(),
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain="day",
            effective_cursor_grain="day",
            start_cursor_config=StartCursorsConfig(max_ahead="1d"),
        )
        for index in range(count)
    ]


def column_names(columns: tuple[ColumnInfo, ...]) -> tuple[str, ...]:
    """Return inspected column names in order."""

    return tuple(column.name for column in columns)


def check_one_source_table(
    *,
    adapter: BaseAdapter,
    connection: object,
    source: SourceEntry,
    listed_source_names: frozenset[str],
) -> None:
    """Run the S405 check for one model that reads one source."""

    model_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL, name="orders"
    )
    source_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SOURCE, name=source.name
    )
    compiled_source: CompiledSource = CompiledSource(
        key=source_key,
        deps=(),
        name=source.name,
        source_entry=source,
        source_file=DiscoveredSourceFile(
            file_path=Path("/project/sources/raw.yml"),
            relative_path=Path("sources/raw.yml"),
            contents=f"sources:\n  - name: {source.name}\n",
            source_entries=(source,),
        ),
    )
    check_selected_source_tables_exist(
        project=cast(CompiledProject, SimpleNamespace(sources=(compiled_source,))),
        adapter=adapter,
        connection=connection,
        scope=PlannerScope(
            upstream_deps={model_key: (source_key,)},
            downstream_deps={source_key: (model_key,)},
            all_keys={"orders": model_key, source.name: source_key},
            models_by_name={},
            selected_keys=frozenset({model_key, source_key}),
            execution_order=(source_key, model_key),
        ),
        relations=PlannerRelationsContext(
            model_locations={},
            seed_locations={},
            function_locations={},
            source_map={source.name: source},
            source_read_map={source.name: source},
            python_source_read_map={},
            source_warehouse_columns={},
            star_exclude_keyword="EXCLUDE",
            listed_source_names=listed_source_names,
        ),
    )
