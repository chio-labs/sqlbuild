//! CTE and relation-alias identity with conservative scope rejection.

use crate::planner_migrations::_helpers::proofs::ast::{
    identifier, items, matching_fields, opaque_field,
};
use crate::planner_migrations::constants::{TABLE_KEY, WITH_KEY};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

fn is_identifier(node: &Value) -> bool {
    identifier(node).is_some() && node.get("quoted").is_some()
}

fn is_relation(node: &Value) -> bool {
    node.is_object() && !is_identifier(node)
}

fn unqualified(node: &Value) -> bool {
    node["schema"].is_null() && node["catalog"].is_null()
}

fn names(node: &Value) -> Vec<String> {
    items(node)
        .iter()
        .filter(|item| is_identifier(item))
        .filter_map(identifier)
        .map(str::to_lowercase)
        .collect()
}

pub(crate) fn local_names(node: &Value) -> Vec<(String, bool)> {
    let mut found: Vec<(String, bool)> = Vec::new();
    match node {
        Value::Array(items) => {
            for item in items {
                found.extend(local_names(item));
            }
        }
        Value::Object(object) => {
            if let Some(with) = object.get("with").filter(|with| with.is_object()) {
                for cte in items(&with["ctes"]).iter().filter(|cte| cte.is_object()) {
                    if is_identifier(&cte["alias"])
                        && let Some(name) = identifier(&cte["alias"])
                    {
                        found.push((name.to_lowercase(), true));
                    }
                }
            }
            for (key, value) in object {
                if opaque_field(key, value) {
                    continue;
                }
                if ["table", "subquery"].contains(&key.as_str())
                    && is_relation(value)
                    && is_identifier(&value["alias"])
                    && let Some(name) = identifier(&value["alias"])
                {
                    found.push((name.to_lowercase(), false));
                }
                found.extend(local_names(value));
            }
        }
        _ => {}
    }
    found
}

fn with_clauses(node: &Value) -> Vec<&Value> {
    matching_fields(node, WITH_KEY)
        .into_iter()
        .filter(|value| value.is_object())
        .collect()
}

fn relation_names(node: &Value) -> BTreeSet<String> {
    matching_fields(node, TABLE_KEY)
        .into_iter()
        .filter(|value| is_relation(value) && unqualified(value) && is_identifier(&value["name"]))
        .filter_map(|value| identifier(&value["name"]))
        .map(str::to_lowercase)
        .collect()
}

pub(crate) fn unambiguous(root: &Value, definitions: &[(String, bool)]) -> bool {
    let top_level = root
        .as_object()
        .filter(|object| object.len() == 1)
        .and_then(|object| object.values().next())
        .map(|statement| &statement["with"]);
    let clauses = with_clauses(root);
    if !clauses.is_empty() && (!top_level.is_some_and(Value::is_object) || clauses.len() > 1) {
        return false;
    }
    let top_level = top_level.unwrap_or(&Value::Null);
    if top_level["recursive"].as_bool() == Some(true) {
        return false;
    }
    let ctes: Vec<&Value> = items(&top_level["ctes"])
        .iter()
        .filter(|cte| cte.is_object())
        .collect();
    let cte_names = names(&Value::Array(
        ctes.iter().map(|cte| cte["alias"].clone()).collect(),
    ));
    if cte_names.len() != ctes.len()
        || cte_names.iter().collect::<BTreeSet<_>>().len() != ctes.len()
    {
        return false;
    }
    for (index, cte) in ctes.iter().enumerate() {
        let references = relation_names(&cte["this"]);
        if cte_names[index..]
            .iter()
            .any(|name| references.contains(name))
        {
            return false;
        }
    }
    let physical = relation_names(root);
    !definitions
        .iter()
        .any(|(name, is_cte)| !is_cte && physical.contains(name) && !cte_names.contains(name))
}

fn renamed(mut node: Value, names: &BTreeMap<String, String>) -> Value {
    if is_identifier(&node)
        && let Some(name) = identifier(&node)
        && let Some(replacement) = names.get(&name.to_lowercase())
    {
        node["name"] = Value::String(replacement.clone());
        node["quoted"] = Value::Bool(false);
    }
    node
}

pub(crate) fn rewrite(
    node: &mut Value,
    names: &BTreeMap<String, String>,
    cte_names: &BTreeMap<String, String>,
) {
    match node {
        Value::Array(items) => items
            .iter_mut()
            .for_each(|item| rewrite(item, names, cte_names)),
        Value::Object(object) => {
            for (key, value) in object {
                if opaque_field(key, value) {
                    continue;
                }
                let original = value.clone();
                rewrite(value, names, cte_names);
                if ["column", "star"].contains(&key.as_str()) && original.is_object() {
                    value["table"] = renamed(original["table"].clone(), names);
                } else if ["table", "subquery"].contains(&key.as_str()) && is_relation(&original) {
                    value["alias"] = renamed(original["alias"].clone(), names);
                    if unqualified(&original) && is_identifier(&original["name"]) {
                        value["name"] = renamed(original["name"].clone(), cte_names);
                    }
                } else if key == WITH_KEY
                    && original.is_object()
                    && let Some(ctes) = value["ctes"].as_array_mut()
                {
                    for cte in ctes {
                        cte["alias"] = renamed(cte["alias"].clone(), names);
                    }
                }
            }
        }
        _ => {}
    }
}
