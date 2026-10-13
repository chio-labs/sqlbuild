//! Strict bounded encoding of integration values and records.

use crate::integration_results::_helpers::bounded::encode;
use crate::integration_results::errors::IntegrationRecordError;
use crate::json::models::JsonValue;

/// Compact ASCII JSON of a bounded value, within the record limit when `record` is set, else the metadata limit.
pub fn encode_integration_value(
    value: &JsonValue,
    record: bool,
) -> Result<String, IntegrationRecordError> {
    encode(value, record)
}
