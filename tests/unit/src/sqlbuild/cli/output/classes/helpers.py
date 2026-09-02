"""Builders for terminal integration-result tests."""


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
