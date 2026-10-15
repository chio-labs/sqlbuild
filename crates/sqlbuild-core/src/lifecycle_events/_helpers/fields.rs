//! Payload value predicates and the per-field type contract.

use crate::json::main::dumps::dumps;
use crate::json::models::{JsonDialect, JsonInteger, JsonValue, StdlibJsonOptions};
use crate::lifecycle_events::constants::{
    BOOLEAN_PAYLOAD_FIELDS, DURATION_MS_FIELD, EXIT_CODE_FIELD, FINITE_NUMBER_PAYLOAD_FIELDS,
    JSON_PAYLOAD_FIELDS, MAX_METADATA_BYTES, METADATA_FIELD, MINIMUM_DURATION_MS,
    NONNEGATIVE_INTEGER_PAYLOAD_FIELDS, STRING_PAYLOAD_FIELDS,
};
use crate::lifecycle_events::models::PayloadValue;
use crate::text::main::python_str_repr::python_str_repr;

/// `payload.get(name)`, treating a JSON null like an absent field.
pub(crate) fn get<'a>(
    payload: &'a [(String, PayloadValue)],
    name: &str,
) -> Option<&'a PayloadValue> {
    payload
        .iter()
        .find(|(key, _)| key == name)
        .map(|(_, value)| value)
        .filter(|value| !matches!(value, PayloadValue::Null))
}

/// The integer a value holds, excluding booleans.
pub(crate) fn integer(value: Option<&PayloadValue>) -> Option<i128> {
    match value {
        Some(PayloadValue::Integer { value, .. }) => Some(*value),
        _ => None,
    }
}

/// Whether a value is text listed in `allowed`.
pub(crate) fn catalogued(value: Option<&PayloadValue>, allowed: &[&str]) -> bool {
    matches!(value, Some(PayloadValue::Text(text)) if allowed.contains(&text.as_str()))
}

fn finite_number(value: &PayloadValue) -> Option<f64> {
    match value {
        PayloadValue::Integer { value, .. } => Some(*value as f64),
        PayloadValue::Float(number) if number.is_finite() => Some(*number),
        _ => None,
    }
}

fn json(value: &PayloadValue) -> JsonValue {
    match value {
        PayloadValue::Null => JsonValue::Null,
        PayloadValue::Bool(flag) => JsonValue::Bool(*flag),
        PayloadValue::Integer { text, .. } => {
            JsonInteger::parse(text).map_or(JsonValue::Null, JsonValue::Integer)
        }
        PayloadValue::Float(number) => JsonValue::Float(*number),
        PayloadValue::Text(text) => JsonValue::String(text.clone()),
        PayloadValue::Array(items) => JsonValue::Array(items.iter().map(json).collect()),
        PayloadValue::Object(entries) => JsonValue::Object(
            entries
                .iter()
                .map(|(key, item)| (key.clone(), json(item)))
                .collect(),
        ),
    }
}

/// The byte length of `json.dumps(value, sort_keys=True, separators=(",", ":"))`.
fn encoded_length(value: &PayloadValue) -> usize {
    let options = StdlibJsonOptions {
        sort_keys: true,
        allow_nan: false,
        ..StdlibJsonOptions::new(None).with_separators(",", ":")
    };
    dumps(&json(value), &JsonDialect::Stdlib(options)).map_or(0, |text| text.len())
}

/// The type contract of one payload field, as the first failing message.
pub(crate) fn field_problem(name: &str, value: &PayloadValue) -> Option<String> {
    let quoted: String = python_str_repr(name);
    if STRING_PAYLOAD_FIELDS.contains(&name) {
        let valid: bool = matches!(value, PayloadValue::Text(text) if !text.is_empty());
        return (!valid).then(|| format!("payload field {quoted} must be a non-empty string"));
    }
    if NONNEGATIVE_INTEGER_PAYLOAD_FIELDS.contains(&name) {
        let valid: bool = integer(Some(value)).is_some_and(|number| number >= 0);
        return (!valid).then(|| {
            format!("payload field {quoted} must be a nonnegative integer excluding bool")
        });
    }
    if FINITE_NUMBER_PAYLOAD_FIELDS.contains(&name) {
        return finite_number(value)
            .is_none()
            .then(|| format!("payload field {quoted} must be a finite number excluding bool"));
    }
    if BOOLEAN_PAYLOAD_FIELDS.contains(&name) {
        return (!matches!(value, PayloadValue::Bool(_)))
            .then(|| format!("payload field {quoted} must be a boolean"));
    }
    if JSON_PAYLOAD_FIELDS.contains(&name) {
        return None;
    }
    if name == DURATION_MS_FIELD {
        let valid: bool = finite_number(value).is_some_and(|number| number >= MINIMUM_DURATION_MS);
        return (!valid).then(|| {
            "payload field 'duration_ms' must be a nonnegative finite number excluding bool"
                .to_owned()
        });
    }
    if name == EXIT_CODE_FIELD {
        return integer(Some(value))
            .is_none()
            .then(|| "payload field 'exit_code' must be an integer excluding bool".to_owned());
    }
    if name == METADATA_FIELD {
        if !matches!(value, PayloadValue::Object(_)) {
            return Some("payload field 'metadata' must be a JSON object".to_owned());
        }
        if encoded_length(value) > MAX_METADATA_BYTES {
            return Some(format!(
                "payload field 'metadata' must encode to at most {MAX_METADATA_BYTES} bytes"
            ));
        }
    }
    None
}
