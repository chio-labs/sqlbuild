//! JSON payload pieces of check output.

use crate::check_command::models::{CheckResultText, CheckStatus};
use crate::json::models::{JsonInteger, JsonValue};

/// A JSON string, or null.
pub(crate) fn text(value: Option<&str>) -> JsonValue {
    value.map_or(JsonValue::Null, |value| JsonValue::String(value.to_owned()))
}

/// A JSON integer.
pub(crate) fn integer(value: usize) -> JsonValue {
    JsonValue::Integer(JsonInteger::from(i64::try_from(value).unwrap_or(i64::MAX)))
}

/// A JSON object with entries in order.
pub(crate) fn object(entries: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(
        entries
            .into_iter()
            .map(|(name, value)| (name.to_owned(), value))
            .collect(),
    )
}

/// The JSON entry of one check.
pub(crate) fn check(result: &CheckResultText) -> JsonValue {
    let warnings: JsonValue = if result.warning_messages.is_empty() {
        JsonValue::Null
    } else {
        JsonValue::Array(
            result
                .warning_messages
                .iter()
                .map(|warning| JsonValue::String(warning.clone()))
                .collect(),
        )
    };
    object(vec![
        ("kind", text(Some("python_check"))),
        ("name", text(Some(&result.name))),
        ("display_name", text(Some(&result.name))),
        (
            "check_id",
            text(Some(&format!("python_check:{}", result.name))),
        ),
        ("status", text(Some(result.status.value()))),
        (
            "passed",
            JsonValue::Bool(result.status == CheckStatus::Pass),
        ),
        ("severity", text(Some(&result.severity))),
        ("message", text(result.message.as_deref())),
        ("error_message", text(result.error_message.as_deref())),
        ("metadata", result.metadata.clone()),
        ("warnings", warnings),
    ])
}
