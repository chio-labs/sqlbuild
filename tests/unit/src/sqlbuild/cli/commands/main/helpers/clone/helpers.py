from __future__ import annotations

from sqlbuild.virtual.executor.models import VirtualCloneItemResult, VirtualCloneResult
from sqlbuild.virtual.state.types import PhysicalArtifactType


def build_virtual_clone_result(*, missing_count: int, skipped_count: int = 0) -> VirtualCloneResult:
    missing_items: tuple[VirtualCloneItemResult, ...] = tuple(
        VirtualCloneItemResult(
            artifact_type=PhysicalArtifactType.MODEL,
            artifact_name=f"missing_{index:02d}",
            version_hash="hash",
            action="missing",
        )
        for index in range(missing_count)
    )
    skipped_items: tuple[VirtualCloneItemResult, ...] = tuple(
        VirtualCloneItemResult(
            artifact_type=PhysicalArtifactType.MODEL,
            artifact_name=f"skipped_{index:02d}",
            version_hash="hash",
            action="skipped_locked",
        )
        for index in range(skipped_count)
    )
    return VirtualCloneResult(
        mode="workspace expected hashes",
        origin_environment="prod",
        destination_environment="dev",
        item_results=missing_items + skipped_items,
    )
