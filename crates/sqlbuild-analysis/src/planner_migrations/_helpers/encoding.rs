//! Python-compatible compact sorted JSON for migration proofs.

use serde_json::Value;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonInteger, JsonValue, StdlibJsonOptions};

pub(crate) fn encode(value: &Value) -> Result<String, String> {
    dumps(
        &converted(value)?,
        &JsonDialect::Stdlib(StdlibJsonOptions {
            sort_keys: true,
            ..StdlibJsonOptions::new(None).with_separators(",", ":")
        }),
    )
    .map_err(|error| format!("{error:?}"))
}

fn converted(value: &Value) -> Result<JsonValue, String> {
    Ok(match value {
        Value::Null => JsonValue::Null,
        Value::Bool(flag) => JsonValue::Bool(*flag),
        Value::String(text) => JsonValue::String(text.clone()),
        Value::Number(number) => {
            if !number.is_f64() {
                JsonValue::Integer(
                    JsonInteger::parse(&number.to_string()).ok_or("invalid integer")?,
                )
            } else {
                JsonValue::Float(number.as_f64().ok_or("invalid float")?)
            }
        }
        Value::Array(items) => {
            JsonValue::Array(items.iter().map(converted).collect::<Result<_, _>>()?)
        }
        Value::Object(object) => JsonValue::Object(
            object
                .iter()
                .map(|(key, value)| Ok((key.clone(), converted(value)?)))
                .collect::<Result<_, String>>()?,
        ),
    })
}
