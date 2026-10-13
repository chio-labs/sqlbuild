//! Reading JSON values with Python's type distinctions.

use crate::integration_results::constants::MAX_IDENTIFIER_CHARS;
use crate::integration_results::errors::IntegrationRecordError;
use crate::json::models::JsonValue;

/// Python `len()` of a string value, or `None` when the value is not a string.
pub(crate) fn text_length(value: &JsonValue) -> Option<usize> {
    match value {
        JsonValue::String(text) => Some(text.chars().count()),
        JsonValue::Utf16(units) => Some(char::decode_utf16(units.iter().copied()).count()),
        _ => None,
    }
}

/// The text of a string value without lone surrogates.
pub(crate) fn text(value: &JsonValue) -> Option<&str> {
    match value {
        JsonValue::String(text) => Some(text),
        _ => None,
    }
}

/// Whether the value is a string equal to one of `allowed`.
pub(crate) fn one_of(value: &JsonValue, allowed: &[&str]) -> bool {
    text(value).is_some_and(|text| allowed.contains(&text))
}

/// The value of `key` in an object, or `Null` when absent.
pub(crate) fn field<'a>(object: &'a [(String, JsonValue)], key: &str) -> &'a JsonValue {
    object
        .iter()
        .find(|(name, _)| name == key)
        .map_or(&JsonValue::Null, |(_, value)| value)
}

/// A non-negative Python `int` (never `bool`).
pub(crate) fn non_negative_integer(value: &JsonValue) -> bool {
    match value {
        JsonValue::Integer(number) => !number.as_str().starts_with('-'),
        _ => false,
    }
}

/// A finite Python `float` (never `int`).
pub(crate) fn finite_float(value: &JsonValue) -> bool {
    matches!(value, JsonValue::Float(number) if number.is_finite())
}

/// `validate_identifier`: a non-empty string of at most the identifier limit.
pub(crate) fn require_identifier(
    value: &JsonValue,
    field_name: &str,
) -> Result<(), IntegrationRecordError> {
    match text_length(value) {
        Some(length) if length > 0 && length <= MAX_IDENTIFIER_CHARS => Ok(()),
        _ => Err(IntegrationRecordError::new(format!(
            "integration {field_name} is invalid"
        ))),
    }
}

/// `validate_optional_identifier`: `null`, or an identifier.
pub(crate) fn optional_identifier(
    value: &JsonValue,
    field_name: &str,
) -> Result<(), IntegrationRecordError> {
    if matches!(value, JsonValue::Null) {
        return Ok(());
    }
    require_identifier(value, field_name)
}

/// The value is `null` or one of `allowed`.
pub(crate) fn null_or_one_of(value: &JsonValue, allowed: &[&str]) -> bool {
    matches!(value, JsonValue::Null) || one_of(value, allowed)
}
