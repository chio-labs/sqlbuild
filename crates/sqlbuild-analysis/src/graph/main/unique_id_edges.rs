use std::collections::HashMap;

use crate::graph::models::{EdgeDirection, ProjectGraph};

/// Each key's neighbours as `prefix.project.name` ids in graph order; unknown types use `model`.
pub fn unique_id_edges(
    graph: &ProjectGraph,
    direction: EdgeDirection,
    project_name: &str,
    prefixes: &HashMap<String, String>,
) -> Vec<(String, Vec<String>)> {
    crate::graph::_helpers::unique_ids::unique_id_edges(graph, direction, project_name, prefixes)
}
