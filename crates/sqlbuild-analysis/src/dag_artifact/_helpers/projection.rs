//! Node lookups the orchestrator projections share.

use std::collections::HashMap;

use crate::dag_artifact::models::DagProjectionGraph;

/// Node index by id; a later node with a repeated id replaces the earlier one.
pub(crate) fn nodes_by_id(graph: &DagProjectionGraph) -> HashMap<&str, usize> {
    graph
        .nodes
        .iter()
        .enumerate()
        .map(|(index, node)| (node.id.as_str(), index))
        .collect()
}

/// Upstream node ids by downstream node id, in edge order.
pub(crate) fn upstream_by_id(graph: &DagProjectionGraph) -> HashMap<&str, Vec<&str>> {
    let mut upstream: HashMap<&str, Vec<&str>> = HashMap::new();
    for (from_id, to_id) in &graph.edges {
        upstream
            .entry(to_id.as_str())
            .or_default()
            .push(from_id.as_str());
    }
    upstream
}
