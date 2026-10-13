//! Decode one integration-result record into its complete canonical form.

use crate::integration_results::_helpers::decoding::{
    RecordParts, decoded_asset, decoded_checks, require_supported, split, with_degraded_default,
};
use crate::integration_results::_helpers::records::{completed, envelope, envelope_fields};
use crate::integration_results::errors::IntegrationRecordError;
use crate::json::models::JsonValue;

/// `IntegrationResultEnvelope.from_json` after JSON parsing: the record with every field, in order.
pub fn normalize_integration_record(
    record: JsonValue,
) -> Result<Vec<(String, JsonValue)>, IntegrationRecordError> {
    let JsonValue::Object(entries) = record else {
        return Err(IntegrationRecordError::new(
            "integration result must be a JSON object",
        ));
    };
    require_supported(&entries)?;
    let parts: RecordParts = split(entries)?;
    let fields: Vec<(String, JsonValue)> = with_degraded_default(parts.envelope)?;
    let asset: JsonValue = decoded_asset(parts.asset)?;
    let checks: Vec<JsonValue> = decoded_checks(parts.checks)?;
    let mut record: Vec<(String, JsonValue)> = completed(fields, &envelope_fields(), &[])?;
    record.push(("asset".to_owned(), asset));
    record.push(("checks".to_owned(), JsonValue::Array(checks)));
    envelope(&record)?;
    Ok(record)
}
