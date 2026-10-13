use sqlbuild_core::json::models::JsonValue;

pub(crate) fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

pub(crate) fn array(items: Vec<JsonValue>) -> JsonValue {
    JsonValue::Array(items)
}
