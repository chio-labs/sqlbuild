//! Drop forward-compatible optional enrichment so an older reader can accept a record.

use crate::integration_results::_helpers::enrichment::stripped_field;
use crate::json::models::JsonValue;

/// The record without optional asset, microbatch-enum and check enrichment.
#[must_use]
pub fn strip_optional_enrichment(record: JsonValue) -> JsonValue {
    let JsonValue::Object(entries) = record else {
        return record;
    };
    JsonValue::Object(entries.into_iter().map(stripped_field).collect())
}
