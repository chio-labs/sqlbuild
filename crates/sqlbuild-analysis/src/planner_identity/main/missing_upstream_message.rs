//! The error message of a selected scope with missing upstreams.

use std::collections::HashMap;

use crate::planner_identity::constants::MISSING_MESSAGE_ITEM_LIMIT;
use crate::planner_identity::models::{GraphKey, MissingUpstream};

/// Missing lineage upstreams by name and, when only an audit or hook read requires one, that read's origin.
pub fn missing_upstream_message(
    missing: &[MissingUpstream],
    edge_origins: &HashMap<(GraphKey, GraphKey), String>,
) -> String {
    let mut lineage_missing: Vec<&MissingUpstream> = Vec::new();
    let mut read_names: Vec<&str> = Vec::new();
    for entry in missing {
        let origins: Vec<&str> = entry
            .required_by
            .iter()
            .filter_map(|dependent| {
                edge_origins
                    .get(&(dependent.clone(), entry.key.clone()))
                    .map(String::as_str)
            })
            .collect();
        if origins.len() < entry.required_by.len() {
            lineage_missing.push(entry);
            continue;
        }
        for origin in origins {
            if !read_names.contains(&origin) {
                read_names.push(origin);
            }
        }
    }
    let mut parts: Vec<String> = Vec::new();
    if !lineage_missing.is_empty() {
        let names: Vec<&str> = lineage_missing
            .iter()
            .take(MISSING_MESSAGE_ITEM_LIMIT)
            .map(|entry| entry.key.name.as_str())
            .collect();
        parts.push(format!(
            "{} missing upstream dependencies ({})",
            lineage_missing.len(),
            names.join(", ")
        ));
    }
    if let [name] = read_names.as_slice() {
        parts.push(format!(
            "{name}, which is not selected and does not exist in the warehouse; select it or build it first"
        ));
    } else if !read_names.is_empty() {
        let shown: String = read_names
            .iter()
            .take(MISSING_MESSAGE_ITEM_LIMIT)
            .copied()
            .collect::<Vec<&str>>()
            .join("; ");
        let more: &str = if read_names.len() > MISSING_MESSAGE_ITEM_LIMIT {
            "; ..."
        } else {
            ""
        };
        parts.push(format!(
            "{} audit reads are not selected and do not exist in the warehouse ({shown}{more}); select them or build them first",
            read_names.len()
        ));
    }
    format!("cannot build selected scope: {}", parts.join("; "))
}
