//! Decode fingerprint metadata as Python's `json.loads` does and write it as `json.dumps(sort_keys=True, separators=(",", ":"))`.

use serde_json::{Map, Value};
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonInteger, JsonValue, StdlibJsonOptions};

/// The decoded top-level object, or None when the text is not a JSON object.
pub(crate) fn decoded_object(metadata_json: &str) -> Result<Option<Map<String, Value>>, ()> {
    match serde_json::from_str::<Value>(metadata_json) {
        Ok(Value::Object(object)) => Ok(Some(object)),
        Ok(_) => Ok(None),
        Err(_) => Err(()),
    }
}

/// `json.dumps(object, sort_keys=True, separators=(",", ":"), default=str)`.
pub(crate) fn canonical_text(object: Map<String, Value>) -> String {
    let dialect: JsonDialect = JsonDialect::Stdlib(StdlibJsonOptions {
        sort_keys: true,
        ..StdlibJsonOptions::new(None).with_separators(",", ":")
    });
    dumps(&json_value(Value::Object(object)), &dialect).unwrap_or_default()
}

/// Python equality of two decoded JSON values: numbers by value and booleans as 0 and 1.
pub(crate) fn python_equal(left: &Value, right: &Value) -> bool {
    match (left, right) {
        (Value::Array(left), Value::Array(right)) => {
            left.len() == right.len()
                && left
                    .iter()
                    .zip(right)
                    .all(|(left, right)| python_equal(left, right))
        }
        (Value::Object(left), Value::Object(right)) => {
            left.len() == right.len()
                && left.iter().all(|(key, value)| {
                    right
                        .get(key)
                        .is_some_and(|other| python_equal(value, other))
                })
        }
        (Value::Number(left_number), Value::Number(right_number))
            if !left_number.is_f64() && !right_number.is_f64() =>
        {
            left_number == right_number
        }
        (Value::Number(_) | Value::Bool(_), Value::Number(_) | Value::Bool(_)) => {
            numeric(left) == numeric(right)
        }
        _ => left == right,
    }
}

fn numeric(value: &Value) -> Option<f64> {
    match value {
        Value::Bool(flag) => Some(f64::from(u8::from(*flag))),
        Value::Number(number) => number.as_f64(),
        _ => None,
    }
}

fn json_value(value: Value) -> JsonValue {
    match value {
        Value::Null => JsonValue::Null,
        Value::Bool(flag) => JsonValue::Bool(flag),
        Value::Number(number) => match JsonInteger::parse(&number.to_string()) {
            Some(integer) if !number.is_f64() => JsonValue::Integer(integer),
            _ => JsonValue::Float(number.as_f64().unwrap_or_default()),
        },
        Value::String(text) => JsonValue::String(text),
        Value::Array(items) => JsonValue::Array(items.into_iter().map(json_value).collect()),
        Value::Object(object) => JsonValue::Object(
            object
                .into_iter()
                .map(|(key, value)| (key, json_value(value)))
                .collect(),
        ),
    }
}
