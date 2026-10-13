//! JSON payload pieces of freshness output.

use crate::freshness_text::models::FreshnessSourceResult;
use crate::json::models::JsonValue;

fn text(value: Option<&str>) -> JsonValue {
    value.map_or(JsonValue::Null, |value| JsonValue::String(value.to_owned()))
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

/// The JSON payload of one source result.
pub(crate) fn source(result: &FreshnessSourceResult) -> JsonValue {
    object(vec![
        ("name", text(Some(&result.name))),
        ("status", text(Some(result.status.value()))),
        ("strategy", text(result.strategy.as_deref())),
        ("value_kind", text(result.value_kind.as_deref())),
        (
            "current_data_version",
            text(result.current_data_version.as_deref()),
        ),
        (
            "previous_data_version",
            text(result.previous_data_version.as_deref()),
        ),
        ("lag_tolerance", text(result.lag_tolerance.as_deref())),
        (
            "target",
            object(vec![
                ("database", text(result.target_database.as_deref())),
                ("schema", text(result.target_schema.as_deref())),
                ("name", text(result.target_name.as_deref())),
            ]),
        ),
        ("message", text(result.message.as_deref())),
        ("age_status", text(result.age_status.as_deref())),
    ])
}
