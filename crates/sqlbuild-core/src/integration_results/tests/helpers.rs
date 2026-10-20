use crate::json::models::{JsonInteger, JsonValue};

pub(super) fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

pub(super) fn integer(value: i64) -> JsonValue {
    JsonValue::Integer(JsonInteger::from(value))
}

pub(super) fn object(entries: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(
        entries
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

/// A completed model asset record with the given asset and occurrence time.
pub(super) fn record(asset: JsonValue, occurred_at: &str) -> JsonValue {
    object(vec![
        ("schema_version", integer(1)),
        ("record_kind", text("integration_result")),
        ("event_id", text("e1")),
        ("event_sequence", integer(0)),
        ("event_type", text("resource_attempt_completed")),
        ("occurred_at", text(occurred_at)),
        ("invocation_id", text("i1")),
        ("run_id", text("r1")),
        ("resource_id", text("model:orders")),
        ("resource_attempt_id", text("a1")),
        ("operation_id", JsonValue::Null),
        ("statement_id", JsonValue::Null),
        ("resource_kind", text("model")),
        ("resource_name", text("orders")),
        ("attempt_number", integer(1)),
        ("duration_ms", integer(3)),
        ("output_kind", text("asset")),
        ("command", text("build")),
        ("asset", asset),
    ])
}

pub(super) fn orders_asset(status: &str) -> JsonValue {
    object(vec![
        ("kind", text("model")),
        ("name", text("orders")),
        ("status", text(status)),
        ("microbatch", object(vec![("run_type", text("normal"))])),
    ])
}

/// A completed audit record whose single check carries the given attachment kind.
pub(super) fn audit_check_record(attachment_kind: &str) -> JsonValue {
    object(vec![
        ("schema_version", integer(1)),
        ("record_kind", text("integration_result")),
        ("event_id", text("e1")),
        ("event_sequence", integer(0)),
        ("event_type", text("resource_attempt_completed")),
        ("occurred_at", text("2026-09-02T12:00:00Z")),
        ("invocation_id", text("i1")),
        ("run_id", text("r1")),
        ("resource_id", text("audit:not_null:orders")),
        ("resource_attempt_id", text("a1")),
        ("operation_id", JsonValue::Null),
        ("statement_id", JsonValue::Null),
        ("resource_kind", text("audit")),
        ("resource_name", text("not_null")),
        ("attempt_number", integer(1)),
        ("duration_ms", integer(3)),
        ("output_kind", text("check")),
        ("command", text("audit")),
        ("asset", JsonValue::Null),
        (
            "checks",
            JsonValue::Array(vec![object(vec![
                ("kind", text("audit")),
                ("name", text("not_null")),
                ("check_id", text("audit:not_null:orders")),
                ("passed", JsonValue::Bool(true)),
                ("status", text("pass")),
                ("attachment_kind", text(attachment_kind)),
                ("audit_definition_name", text("not_null")),
            ])]),
        ),
    ])
}
