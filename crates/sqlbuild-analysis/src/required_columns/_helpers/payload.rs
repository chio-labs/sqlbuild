//! Expression payloads as the Polyglot wheel's `args` exposed them, and walks over them.

use polyglot_sql::{Expression, ast_json};
use serde_json::{Map, Value};

use crate::required_columns::_helpers::tree::payload;
use crate::required_columns::constants::{
    KIND_COLUMN, KIND_SELECT, KIND_SUBQUERY, SET_OPERATION_KINDS,
};

/// `expression.args.get(key)`, unless the wheel exposed it as expression objects.
pub(crate) fn arg(expression: &Expression, key: &str) -> Option<Value> {
    plain_value(payload(expression).remove(key))
}

/// `value`, unless the wheel exposed it as an expression or a list of expressions.
pub(crate) fn plain_value(value: Option<Value>) -> Option<Value> {
    let value: Value = value?;
    ast_json::expression_from_value(value.clone()).err()?;
    ast_json::expressions_from_value(value.clone()).err()?;
    Some(value)
}

/// `_payload_name`: a payload mapping's string `name`, else empty.
pub(crate) fn payload_name(payload: Option<&Value>) -> String {
    payload
        .and_then(Value::as_object)
        .and_then(|map| map.get("name"))
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_owned()
}

/// `_column_refs_in_payload`: each column outside nested queries, in the wheel's sorted key order.
pub(crate) fn column_refs_in_payload(payload: Option<&Value>) -> Vec<(String, String)> {
    match payload {
        Some(Value::Array(items)) => items
            .iter()
            .flat_map(|item| column_refs_in_payload(Some(item)))
            .collect(),
        Some(Value::Object(map)) => object_column_refs(map),
        _ => Vec::new(),
    }
}

fn object_column_refs(map: &Map<String, Value>) -> Vec<(String, String)> {
    let nested_query: bool = map.contains_key(KIND_SUBQUERY)
        || map.contains_key(KIND_SELECT)
        || SET_OPERATION_KINDS
            .iter()
            .any(|kind| map.contains_key(*kind));
    if nested_query {
        return Vec::new();
    }
    if let Some(Value::Object(column)) = map.get(KIND_COLUMN) {
        return vec![(
            payload_name(column.get("name")),
            payload_name(column.get("table")),
        )];
    }
    let mut keys: Vec<&String> = map.keys().collect();
    keys.sort();
    keys.into_iter()
        .flat_map(|key| column_refs_in_payload(map.get(key)))
        .collect()
}
