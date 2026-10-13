use sqlbuild_core::json::models::{JsonInteger, JsonValue};

pub(crate) fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

pub(crate) fn integer(value: i64) -> JsonValue {
    JsonValue::Integer(JsonInteger::from(value))
}
