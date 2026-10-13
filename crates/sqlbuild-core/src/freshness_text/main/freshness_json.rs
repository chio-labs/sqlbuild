//! The JSON payload of `sqb freshness`.

use crate::freshness_text::_helpers::counts::{age_count, status_count};
use crate::freshness_text::_helpers::json_payload::{object, source};
use crate::freshness_text::constants::{AGE_SUMMARY, STATUS_SUMMARY};
use crate::freshness_text::models::FreshnessSourceResult;
use crate::json::errors::JsonEmitError;
use crate::json::main::dumps::dumps;
use crate::json::models::{JsonDialect, JsonInteger, JsonValue, StdlibJsonOptions};

/// Sources and summary counts, as `json.dumps(..., indent=2)` without a trailing newline.
pub fn freshness_json(results: &[FreshnessSourceResult]) -> Result<String, JsonEmitError> {
    let mut summary: Vec<(&str, JsonValue)> = STATUS_SUMMARY
        .iter()
        .map(|(_, key, status)| {
            (
                *key,
                JsonValue::Integer(JsonInteger::from(status_count(results, *status))),
            )
        })
        .collect();
    summary.extend(AGE_SUMMARY.iter().map(|(_, key, age)| {
        (
            *key,
            JsonValue::Integer(JsonInteger::from(age_count(results, age))),
        )
    }));
    let payload: JsonValue = object(vec![
        (
            "sources",
            JsonValue::Array(results.iter().map(source).collect()),
        ),
        ("summary", object(summary)),
    ]);
    dumps(
        &payload,
        &JsonDialect::Stdlib(StdlibJsonOptions::new(Some(2))),
    )
}
