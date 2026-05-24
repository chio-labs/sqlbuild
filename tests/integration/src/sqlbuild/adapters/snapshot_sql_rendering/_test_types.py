from dataclasses import dataclass

from sqlbuild.adapter.base.base_adapter import BaseAdapter


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
