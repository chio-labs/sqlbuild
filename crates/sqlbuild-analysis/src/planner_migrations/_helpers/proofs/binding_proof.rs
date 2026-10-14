//! Conservative alias resolution in unchanged and renamed projections.

use crate::planner_migrations::_helpers::proofs::ast::identifier;
use crate::planner_migrations::models::QueryShape;
use serde_json::Value;
use std::collections::BTreeSet;

pub(crate) fn other_references(shape: &QueryShape, excluded: &str) -> BTreeSet<String> {
    shape
        .projections
        .iter()
        .filter(|item| item.name.to_lowercase() != excluded)
        .flat_map(|item| item.references.iter().cloned())
        .collect()
}

pub(crate) fn binding_proven<E>(
    shapes: (&QueryShape, &QueryShape),
    names: (&str, &str),
    input_columns: &mut impl FnMut(&str, &str) -> Result<Option<BTreeSet<String>>, E>,
) -> Result<bool, E> {
    let (previous, current) = shapes;
    let (origin, destination) = names;
    let mut referenced = previous.clause_references.clone();
    referenced.extend(current.clause_references.iter().cloned());
    referenced.extend(other_references(previous, origin));
    referenced.extend(other_references(current, destination));
    if !referenced.contains(origin) && !referenced.contains(destination) {
        return Ok(true);
    }
    let Some(relations) = &current.input_relations else {
        return Ok(false);
    };
    let mut inputs = current.local_input_columns.clone();
    for (kind, name) in relations {
        let Some(columns) = input_columns(kind, name)? else {
            return Ok(false);
        };
        inputs.extend(columns);
    }
    if inputs.contains(destination) {
        return Ok(false);
    }
    if inputs.contains(origin) {
        return Ok(previous
            .projections
            .iter()
            .any(|item| item.name.to_lowercase() == origin && item.passthrough));
    }
    Ok(!current.clause_references.contains(origin)
        && !other_references(current, "").contains(origin))
}

pub(crate) fn substitute(node: &mut Value, names: &[(String, String)]) {
    match node {
        Value::Array(items) => items.iter_mut().for_each(|item| substitute(item, names)),
        Value::Object(object) => {
            if object.contains_key("select") {
                return;
            }
            if let Some(column) = object.get_mut("column").filter(|column| column.is_object())
                && column["table"].is_null()
                && column["name"]["quoted"] == false
                && let Some(name) = identifier(&column["name"])
                && let Some((_, replacement)) = names.iter().rev().find(|(key, _)| key == name)
            {
                column["name"]["name"] = Value::String(replacement.clone());
                return;
            }
            object
                .values_mut()
                .for_each(|value| substitute(value, names));
        }
        _ => {}
    }
}
