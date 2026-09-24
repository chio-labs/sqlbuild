from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter


@dataclass(frozen=True)
class SnapshotSqlRenderingAdapterTestCase:
    description: str
    adapter: BaseAdapter
    expected_create_initial_fragments: tuple[str, ...]
    expected_timestamp_hard_delete_fragments: tuple[str, ...]
    expected_historical_check_initial_hard_delete_fragments: tuple[str, ...]
    expected_historical_timestamp_initial_hard_delete_fragments: tuple[str, ...]
    expected_historical_timestamp_apply_hard_delete_fragments: tuple[str, ...]
    expected_historical_check_apply_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SnapshotReappearanceRenderingTestCase:
    description: str
    adapter: BaseAdapter
    expected_initial_fragments: tuple[str, ...]
    expected_apply_fragments: tuple[str, ...]
    unexpected_apply_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SnapshotExecutionTestCase:
    """One adapter executing one snapshot scenario through one build path on DuckDB."""

    description: str
    adapter_type: type[BaseAdapter]
    normalize_sql: Callable[[str], str]
    source_select_sql: Callable[[tuple[object, ...]], str]
    render_initial: Callable[[BaseAdapter], tuple[str, ...]]
    render_apply: Callable[[BaseAdapter], tuple[str, ...]]
    history_sql: str
    builds: tuple[tuple[tuple[object, ...], ...], ...]
    expected_history: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SqlServerSnapshotRenderingTestCase:
    """SQL Server snapshot renders that must stay valid T-SQL."""

    description: str
    unexpected_fragments: tuple[str, ...]
    expected_changes_apply_prefix: str
    expected_changes_apply_fragments: tuple[str, ...]
