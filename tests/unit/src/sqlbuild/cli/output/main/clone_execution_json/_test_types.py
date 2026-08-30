from dataclasses import dataclass

from sqlbuild.executor.clone.models import CloneItemResult


@dataclass(frozen=True)
class CloneExecutionJsonTestCase:
    description: str
    item_results: tuple[CloneItemResult, ...]
    expected_status: str
    expected_asset_statuses: tuple[str, ...]
    expected_asset_actions: tuple[str, ...]
    expected_summary: dict[str, int]


@dataclass(frozen=True)
class CloneItemExecutionEventTestCase:
    description: str
    item: CloneItemResult
    resource_type: str
    expected_asset: dict[str, object]


@dataclass(frozen=True)
class VirtualCloneExecutionJsonTestCase:
    description: str
    expected_status: str
    expected_asset_statuses: tuple[str, ...]
    expected_summary: dict[str, int]
