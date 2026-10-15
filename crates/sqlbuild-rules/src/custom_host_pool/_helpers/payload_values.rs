//! Python `str()` of host payload values.

use serde_json::Value;

use crate::custom_host_pool::types::FactKey;

/// `str(value)` for the scalar JSON values a host writes.
pub(crate) fn python_text(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        Value::Null => "None".to_owned(),
        Value::Bool(true) => "True".to_owned(),
        Value::Bool(false) => "False".to_owned(),
        Value::Number(_) | Value::Array(_) | Value::Object(_) => value.to_string(),
    }
}

/// `tuple(map(str, key))` for one recorded fact key.
pub(crate) fn fact_key(value: &Value) -> FactKey {
    match value {
        Value::Array(parts) => parts.iter().map(python_text).collect(),
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) | Value::Object(_) => {
            Vec::new()
        }
    }
}

/// `tuple(tuple(map(str, key)) for key in value)` for one read set.
pub(crate) fn readset(value: &Value) -> Vec<FactKey> {
    match value {
        Value::Array(keys) => keys.iter().map(fact_key).collect(),
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) | Value::Object(_) => {
            Vec::new()
        }
    }
}
