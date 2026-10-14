//! Canonical migration AST values.

use crate::planner_migrations::constants::{HAVING_MAX_KEY, OPAQUE_TUPLE_FIELDS};
use serde_json::Value;
use std::collections::BTreeSet;

/// Tuple-valued AST fields are opaque to the historical Python dict/list walkers.
pub(crate) fn opaque_field(key: &str, value: &Value) -> bool {
    key == HAVING_MAX_KEY
        || (OPAQUE_TUPLE_FIELDS.contains(&key)
            && value
                .as_array()
                .is_some_and(|items| !items.is_empty() && items.iter().all(Value::is_array)))
}

pub(crate) fn strip_formatting(node: &mut Value) {
    match node {
        Value::Object(object) => {
            object.shift_remove("span");
            for (key, value) in object {
                if opaque_field(key, value) {
                    continue;
                }
                if key.ends_with("comments") {
                    *value = Value::Array(Vec::new());
                } else {
                    strip_formatting(value);
                }
            }
        }
        Value::Array(items) => items.iter_mut().for_each(strip_formatting),
        _ => {}
    }
}

pub(crate) fn canonical(node: &mut Value) {
    match node {
        Value::Array(items) => items.iter_mut().for_each(canonical),
        Value::Object(object) => {
            for (key, value) in object.iter_mut() {
                if !opaque_field(key, value) {
                    canonical(value);
                }
            }
            if object.get("quoted") == Some(&Value::Bool(false))
                && let Some(Value::String(name)) = object.get_mut("name")
            {
                *name = name.to_lowercase();
            }
        }
        _ => {}
    }
}

pub(crate) fn identifier(node: &Value) -> Option<&str> {
    node.get("name")?.as_str()
}

pub(crate) fn identifiers(node: &Value) -> Vec<String> {
    items(node)
        .iter()
        .filter_map(identifier)
        .map(str::to_lowercase)
        .collect()
}

pub(crate) fn items(node: &Value) -> &[Value] {
    node.as_array().map_or(&[], Vec::as_slice)
}

pub(crate) fn clause_items(node: &Value) -> &[Value] {
    if node.is_array() {
        items(node)
    } else {
        items(&node["expressions"])
    }
}

pub(crate) fn references(node: &Value, unqualified: bool) -> BTreeSet<String> {
    matching_fields(node, "column")
        .into_iter()
        .filter(|column| !unqualified || column["table"].is_null())
        .filter_map(|column| identifier(&column["name"]))
        .map(str::to_lowercase)
        .collect()
}

pub(crate) fn matching_fields<'a>(node: &'a Value, key: &str) -> Vec<&'a Value> {
    let mut found: Vec<&Value> = Vec::new();
    let mut pending: Vec<&Value> = vec![node];
    while let Some(current) = pending.pop() {
        match current {
            Value::Array(items) => pending.extend(items),
            Value::Object(object) => {
                if let Some(value) = object.get(key) {
                    found.push(value);
                }
                pending.extend(
                    object
                        .iter()
                        .filter(|(key, value)| !opaque_field(key, value))
                        .map(|(_, value)| value),
                );
            }
            _ => {}
        }
    }
    found
}
