//! `str()` of a decoded JSON value, as Python prints the value `json.loads` returns.

use serde_json::Value;
use sqlbuild_core::json::main::python_float_repr::python_float_repr;

use crate::events::constants::{PYTHON_FALSE, PYTHON_NONE, PYTHON_TRUE};

/// Python's `str()` of a JSON scalar; containers keep their compact JSON text.
pub(crate) fn python_text(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        Value::Bool(true) => PYTHON_TRUE.to_owned(),
        Value::Bool(false) => PYTHON_FALSE.to_owned(),
        Value::Null => PYTHON_NONE.to_owned(),
        Value::Number(number) => match number.as_f64() {
            Some(float) if number.is_f64() => python_float_repr(float),
            _ => number.to_string(),
        },
        Value::Array(_) | Value::Object(_) => value.to_string(),
    }
}
