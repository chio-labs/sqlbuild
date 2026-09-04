"""Builders for terminal integration-result tests."""

from collections.abc import Mapping
from typing import cast

from sqlbuild.cli.output.models import IntegrationAssetResult
from sqlbuild.runtime.observability.types import JSONValue


def build_valid_integration_payload() -> dict[str, object]:
    """Return one valid canonical asset integration envelope mapping."""

    return {
        "schema_version": 1,
        "record_kind": "integration_result",
        "event_id": "event-orders",
        "event_sequence": 0,
        "event_type": "resource_attempt_completed",
        "occurred_at": "2026-09-02T12:00:00+00:00",
        "invocation_id": "invocation-1",
        "run_id": "run-1",
        "resource_id": "model:orders",
        "resource_attempt_id": "attempt-orders",
        "operation_id": None,
        "statement_id": None,
        "resource_kind": "model",
        "resource_name": "orders",
        "attempt_number": 1,
        "duration_ms": 1,
        "output_kind": "asset",
        "command": "build",
        "error_code": None,
        "error_type": None,
        "skip_code": None,
        "skip_mode": None,
        "asset": {"kind": "model", "name": "orders", "status": "success"},
        "checks": [],
    }


def build_maximum_start_safety(action: str) -> Mapping[str, JSONValue]:
    """Return valid maximum-start metadata for one canonical action."""

    return cast(
        dict[str, JSONValue],
        {
            "action": action,
            "max_ahead": "0d",
            "invocation_time": "2026-09-02T12:00:00+00:00",
            "physical_target_max": "2026-09-03",
            "highest_eligible_target_max": "2026-09-02",
            "effective_start": "2026-09-02",
            "maximum_allowed_start": "2026-09-02",
            "input": {"relation": "main.orders", "cursor_column": "order_date"},
        },
    )


def build_integration_asset_with_maximum_start(action: str) -> IntegrationAssetResult:
    """Construct an asset carrying canonical maximum-start action metadata."""

    return IntegrationAssetResult(
        kind="model",
        name="orders",
        status="success",
        maximum_start_safety=build_maximum_start_safety(action),
    )
