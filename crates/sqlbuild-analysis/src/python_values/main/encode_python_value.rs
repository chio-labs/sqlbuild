//! The JSON value `json.dumps` encodes, or the `TypeError` it raises first in output order.

use sqlbuild_core::json::models::JsonValue;

use crate::python_values::models::PythonValue;

/// The encoded value, or the message of the first `TypeError` in output order.
pub fn encode_python_value(value: PythonValue) -> Result<JsonValue, String> {
    Ok(match value {
        PythonValue::Null => JsonValue::Null,
        PythonValue::Bool(flag) => JsonValue::Bool(flag),
        PythonValue::Integer(number) => JsonValue::Integer(number),
        PythonValue::Float(number) => JsonValue::Float(number),
        PythonValue::String(text) => JsonValue::String(text),
        PythonValue::Utf16(units) => JsonValue::Utf16(units),
        PythonValue::Array(items) => JsonValue::Array(
            items
                .into_iter()
                .map(encode_python_value)
                .collect::<Result<_, _>>()?,
        ),
        PythonValue::Object(entries) => JsonValue::Object(
            entries
                .into_iter()
                .map(|(key, item)| Ok((key.text?, encode_python_value(item)?)))
                .collect::<Result<_, String>>()?,
        ),
        PythonValue::Unencodable(message) => return Err(message),
    })
}
