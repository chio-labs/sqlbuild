//! Write identity hashes from the upstream hashes actually available this run.

use std::collections::HashSet;

use crate::planner_identity::_helpers::identity_resolver::IdentityResolver;
use crate::planner_identity::models::{GraphKey, IdentityGraph};

/// The base hashes with each selected node recomposed from upstream write hashes, in first-recorded order.
pub fn graph_write_identity_hashes(
    graph: &IdentityGraph,
    selected_keys: &HashSet<GraphKey>,
    base_hashes: Vec<(GraphKey, String)>,
) -> Vec<(GraphKey, String)> {
    let mut resolver = IdentityResolver::new(&graph.nodes, Some(selected_keys), base_hashes);
    for key in &graph.execution_order {
        let _ = resolver.resolve_write(key);
    }
    let mut hashes: Vec<(GraphKey, String)> = Vec::new();
    for (key, hash) in resolver.into_hashes() {
        if let Some(hash) = hash {
            hashes.push((key, hash));
        }
    }
    hashes
}
