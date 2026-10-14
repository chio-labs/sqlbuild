//! Non-projection clauses and positional references of a SELECT.

use crate::planner_migrations::_helpers::proofs::ast::{clause_items, items, references};
use crate::planner_migrations::constants::NUMBER_LITERAL;
use serde_json::Value;
use std::collections::BTreeSet;

pub(crate) fn clause_references(select: &Value) -> BTreeSet<String> {
    let clauses: Vec<Value> = select
        .as_object()
        .into_iter()
        .flat_map(|object| object.iter())
        .filter(|(key, _)| !["expressions", "with", "from", "joins"].contains(&key.as_str()))
        .map(|(_, value)| value.clone())
        .chain(
            items(&select["joins"])
                .iter()
                .filter(|join| join.is_object())
                .map(|join| join["on"].clone()),
        )
        .collect();
    references(&Value::Array(clauses), true)
}

pub(crate) fn positional(select: &Value) -> bool {
    clause_items(&select["group_by"])
        .iter()
        .chain(clause_items(&select["order_by"]).iter().map(|item| {
            if item.is_object() {
                &item["this"]
            } else {
                item
            }
        }))
        .chain(clause_items(&select["distinct_on"]))
        .any(|item| item["literal"]["literal_type"] == NUMBER_LITERAL)
}
