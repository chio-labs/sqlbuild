//! The phases of decoding one record: identity, its parts, and its checks.

use crate::integration_results::_helpers::bounded::has_key;
use crate::integration_results::_helpers::records::{asset, check, invalid_envelope};
use crate::integration_results::_helpers::values::{field, one_of};
use crate::integration_results::constants::{
    ASSET_OUTPUT, AUDIT_SEVERITIES, CHECK_OUTPUT, MAX_COLLECTION_ITEMS, PROJECTION_DEGRADED_FIELD,
    RECORD_KIND, SCHEMA_VERSION,
};
use crate::integration_results::errors::IntegrationRecordError;
use crate::json::models::{JsonInteger, JsonValue};

type Entries = Vec<(String, JsonValue)>;

/// The record's envelope fields, its asset and its checks.
pub(crate) struct RecordParts {
    pub(crate) envelope: Entries,
    pub(crate) asset: JsonValue,
    pub(crate) checks: Vec<JsonValue>,
}

/// A value as Python's `str()` shows it in an error message.
fn shown(value: &JsonValue) -> String {
    match value {
        JsonValue::Null => "None".to_owned(),
        JsonValue::String(text) => text.clone(),
        JsonValue::Integer(number) => number.as_str().to_owned(),
        JsonValue::Bool(flag) => if *flag { "True" } else { "False" }.to_owned(),
        other => format!("{other:?}"),
    }
}

/// The record's schema version and kind are the supported ones.
pub(crate) fn require_supported(
    entries: &[(String, JsonValue)],
) -> Result<(), IntegrationRecordError> {
    let version: &JsonValue = field(entries, "schema_version");
    if *version != JsonValue::Integer(JsonInteger::from(SCHEMA_VERSION)) {
        return Err(IntegrationRecordError::new(format!(
            "unsupported integration result schema_version: {}",
            shown(version)
        )));
    }
    let kind: &JsonValue = field(entries, "record_kind");
    if !one_of(kind, &[RECORD_KIND]) {
        return Err(IntegrationRecordError::new(format!(
            "unsupported integration result record_kind: {}",
            shown(kind)
        )));
    }
    Ok(())
}

/// The record split into its envelope fields, raw asset and raw checks.
pub(crate) fn split(entries: Entries) -> Result<RecordParts, IntegrationRecordError> {
    let mut parts: RecordParts = RecordParts {
        envelope: Vec::with_capacity(entries.len()),
        asset: JsonValue::Null,
        checks: Vec::new(),
    };
    for (key, value) in entries {
        match (key.as_str(), value) {
            ("asset", value @ (JsonValue::Null | JsonValue::Object(_))) => parts.asset = value,
            ("checks", JsonValue::Array(items)) => parts.checks = items,
            ("asset", _) => {
                return Err(IntegrationRecordError::new(
                    "integration result asset must be an object",
                ));
            }
            ("checks", _) => {
                return Err(IntegrationRecordError::new(
                    "integration result checks must be an array",
                ));
            }
            (_, value) => parts.envelope.push((key, value)),
        }
    }
    if parts.checks.len() > MAX_COLLECTION_ITEMS {
        return Err(IntegrationRecordError::new(
            "integration result checks exceed item limit",
        ));
    }
    Ok(parts)
}

/// The record's envelope fields with the default `projection_degraded`.
pub(crate) fn with_degraded_default(
    mut envelope: Entries,
) -> Result<Entries, IntegrationRecordError> {
    if !one_of(
        field(&envelope, "output_kind"),
        &[ASSET_OUTPUT, CHECK_OUTPUT],
    ) {
        return Err(invalid_envelope());
    }
    if !has_key(&envelope, PROJECTION_DEGRADED_FIELD) {
        envelope.push((PROJECTION_DEGRADED_FIELD.to_owned(), JsonValue::Bool(false)));
    }
    Ok(envelope)
}

/// `IntegrationAssetResult(**asset)` of a raw asset, or `null`.
pub(crate) fn decoded_asset(raw: JsonValue) -> Result<JsonValue, IntegrationRecordError> {
    match raw {
        JsonValue::Object(object) => Ok(JsonValue::Object(asset(object)?)),
        _ => Ok(JsonValue::Null),
    }
}

/// `IntegrationCheckResult(**check)` of every raw check.
pub(crate) fn decoded_checks(
    raw: Vec<JsonValue>,
) -> Result<Vec<JsonValue>, IntegrationRecordError> {
    let mut decoded: Vec<JsonValue> = Vec::with_capacity(raw.len());
    for item in raw {
        let JsonValue::Object(entries) = item else {
            return Err(IntegrationRecordError::new(
                "integration result checks must contain only objects",
            ));
        };
        let severity: &JsonValue = field(&entries, "severity");
        if !matches!(severity, JsonValue::Null) && !one_of(severity, &AUDIT_SEVERITIES) {
            return Err(IntegrationRecordError::new(format!(
                "integration check severity must be one of: {}",
                AUDIT_SEVERITIES.join(", ")
            )));
        }
        decoded.push(JsonValue::Object(check(entries)?));
    }
    Ok(decoded)
}
