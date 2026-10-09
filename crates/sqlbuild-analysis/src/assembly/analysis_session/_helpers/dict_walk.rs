//! Python's dict walk over a parsed query's `to_dict()` payload, on the same serde values.

use serde_json::{Map, Value};

use crate::assembly::analysis_session::constants::{
    COLUMN_AST_KIND, DEPENDENCY_FUNCTION_NAMES, FUNCTION_AST_KIND, RENDERED_TYPE_NAMES,
    STAR_AST_KIND, TABLE_AST_KIND,
};

/// Python's `bool(value)`.
pub(crate) fn truthy(value: Option<&Value>) -> bool {
    match value {
        Some(Value::Bool(flag)) => *flag,
        Some(Value::Null) | None => false,
        Some(Value::String(text)) => !text.is_empty(),
        Some(Value::Array(items)) => !items.is_empty(),
        Some(Value::Object(items)) => !items.is_empty(),
        Some(Value::Number(number)) => number.as_f64() != Some(0.0),
    }
}

/// The single key of a one-key object, or "" for anything else.
pub(crate) fn node_key(node: Option<&Value>) -> &str {
    let Some(object) = node
        .and_then(Value::as_object)
        .filter(|object| object.len() == 1)
    else {
        return "";
    };
    object.keys().next().map_or("", String::as_str)
}

/// The payload under a node's single key.
pub(crate) fn payload(node: Option<&Value>) -> Option<&Map<String, Value>> {
    let key: &str = node_key(node);
    node.and_then(|node| node.get(key))
        .and_then(Value::as_object)
}

/// Python's `_dict_list`: the objects of a list, or nothing.
pub(crate) fn dict_list(value: Option<&Value>) -> Vec<&Value> {
    match value.and_then(Value::as_array) {
        Some(items) => objects(items),
        None => Vec::new(),
    }
}

fn objects(items: &[Value]) -> Vec<&Value> {
    items.iter().filter(|item| item.is_object()).collect()
}

/// Python's `_nested`: follow object keys.
pub(crate) fn nested<'a>(node: Option<&'a Value>, keys: &[&str]) -> Option<&'a Value> {
    let mut current: Option<&Value> = node;
    for key in keys {
        current = current
            .and_then(Value::as_object)
            .and_then(|object| object.get(*key));
    }
    current
}

/// Python's `_identifier_name`.
pub(crate) fn identifier_name(node: Option<&Value>) -> Option<&str> {
    match node {
        Some(Value::String(name)) => Some(name),
        Some(Value::Object(object)) => object
            .get("name")
            .and_then(Value::as_str)
            .filter(|name| !name.is_empty()),
        _ => None,
    }
}

/// Python's `_column_name`.
pub(crate) fn column_name(node: Option<&Value>) -> Option<&str> {
    if node_key(node) != COLUMN_AST_KIND {
        return None;
    }
    identifier_name(payload(node)?.get("name"))
}

/// Python's `_relation_name`: a table, a column or a dependency call's first argument.
pub(crate) fn relation_name(node: Option<&Value>) -> Option<&str> {
    let key: &str = node_key(node);
    let payload: &Map<String, Value> = payload(node)?;
    if key == TABLE_AST_KIND || key == COLUMN_AST_KIND {
        return identifier_name(payload.get("name"));
    }
    let called: &str = payload
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if key == FUNCTION_AST_KIND && DEPENDENCY_FUNCTION_NAMES.contains(&casefold(called).as_str()) {
        return column_name(dict_list(payload.get("args")).first().copied());
    }
    None
}

/// Python's `_is_single_wildcard`.
pub(crate) fn is_single_wildcard(value: Option<&Value>) -> bool {
    let expressions: Vec<&Value> = dict_list(value);
    let [only] = expressions.as_slice() else {
        return false;
    };
    if node_key(Some(only)) != STAR_AST_KIND {
        return false;
    }
    let Some(star) = only.get(STAR_AST_KIND).and_then(Value::as_object) else {
        return false;
    };
    !["except", "replace", "rename", "table"]
        .iter()
        .any(|key| truthy(star.get(*key)))
}

/// Python's `_render_type` of a cast target.
pub(crate) fn render_type(node: Option<&Value>) -> Option<String> {
    let node: &Map<String, Value> = node?.as_object()?;
    let raw_type: &str = node
        .get("data_type")
        .and_then(Value::as_str)
        .filter(|raw| !raw.is_empty())?;
    let folded: String = casefold(raw_type);
    let rendered: String = RENDERED_TYPE_NAMES
        .iter()
        .find(|(name, _)| *name == folded)
        .map_or_else(
            || raw_type.replace('_', " ").to_ascii_uppercase(),
            |(_, rendered)| (*rendered).to_owned(),
        );
    if let Some(length) = python_int(node.get("length")) {
        return Some(format!("{rendered}({length})"));
    }
    let Some(precision) = python_int(node.get("precision")) else {
        return Some(rendered);
    };
    Some(match python_int(node.get("scale")) {
        Some(scale) => format!("{rendered}({precision}, {scale})"),
        None => format!("{rendered}({precision})"),
    })
}

/// Python's `str(value)` for a value `isinstance(value, int)` accepts.
fn python_int(value: Option<&Value>) -> Option<String> {
    match value? {
        Value::Bool(flag) => Some(if *flag { "True" } else { "False" }.to_owned()),
        Value::Number(number) if number.is_i64() || number.is_u64() => Some(number.to_string()),
        _ => None,
    }
}

/// Python's `str.casefold` for the ASCII text a pivot proof compares.
pub(crate) fn casefold(text: &str) -> String {
    text.to_ascii_lowercase()
}
