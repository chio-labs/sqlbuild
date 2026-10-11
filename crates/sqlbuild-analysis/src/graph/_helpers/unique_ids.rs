//! Edges written as dbt-style `prefix.project.name` unique ids, as the manifest stores them.

use std::collections::HashMap;

use crate::assembly::project::types::ObjectKey;
use crate::graph::constants::DEFAULT_UNIQUE_ID_PREFIX;
use crate::graph::models::{EdgeDirection, ProjectGraph};

pub(crate) fn unique_id_edges(
    graph: &ProjectGraph,
    direction: EdgeDirection,
    project_name: &str,
    prefixes: &HashMap<String, String>,
) -> Vec<(String, Vec<String>)> {
    let entries: &[(ObjectKey, Vec<ObjectKey>)] = match direction {
        EdgeDirection::Upstream => &graph.upstream,
        EdgeDirection::Downstream => &graph.downstream,
    };
    entries
        .iter()
        .map(|(key, neighbours)| {
            (
                unique_id(key, project_name, prefixes),
                unique_ids(neighbours, project_name, prefixes),
            )
        })
        .collect()
}

fn unique_ids(
    keys: &[ObjectKey],
    project_name: &str,
    prefixes: &HashMap<String, String>,
) -> Vec<String> {
    keys.iter()
        .map(|key| unique_id(key, project_name, prefixes))
        .collect()
}

fn unique_id(key: &ObjectKey, project_name: &str, prefixes: &HashMap<String, String>) -> String {
    let prefix: &str = prefixes
        .get(&key.0)
        .map_or(DEFAULT_UNIQUE_ID_PREFIX, String::as_str);
    format!("{prefix}.{project_name}.{}", key.1)
}
