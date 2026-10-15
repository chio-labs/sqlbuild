use sqlbuild_core::json::models::{JsonInteger, JsonValue};
use std::collections::HashSet;

pub(crate) fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

pub(crate) fn integer(value: i64) -> JsonValue {
    JsonValue::Integer(JsonInteger::from(value))
}

/// The keys of `keys` seen more than once, in first-repeat order.
pub(super) fn duplicates(keys: &[&'static str]) -> Vec<&'static str> {
    let mut seen: HashSet<&str> = HashSet::new();
    keys.iter()
        .copied()
        .filter(|key| !seen.insert(key))
        .collect()
}
