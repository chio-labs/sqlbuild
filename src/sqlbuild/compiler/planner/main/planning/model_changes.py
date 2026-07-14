"""Public entrypoint for one-model change detection."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.planner._helpers.changes.detect import (
    detect_model_changes as _detect_model_changes,
)
from sqlbuild.compiler.planner.models import ChangeDetectionResult, WarehouseSnapshot


def detect_model_changes(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    sql_analysis_enabled: bool,
    query_change_tracking: bool,
    full_refresh: bool,
    function_local_hashes: dict[str, str] | None = None,
    expected_version_hash: str | None = None,
    expected_metadata_json: str | None = None,
) -> ChangeDetectionResult:
    """Detect changes for one model and resolve backfill policy."""

    return _detect_model_changes(
        model=model,
        snapshot=snapshot,
        sql_analysis_enabled=sql_analysis_enabled,
        query_change_tracking=query_change_tracking,
        full_refresh=full_refresh,
        function_local_hashes=function_local_hashes,
        expected_version_hash=expected_version_hash,
        expected_metadata_json=expected_metadata_json,
    )
