//! Expected identity hashes of every node of a dependency graph.

use crate::planner_identity::_helpers::identity_resolver::IdentityResolver;
use crate::planner_identity::models::IdentityGraph;
use crate::planner_identity::types::IdentityHashes;

/// Each node's hash composed from its upstream expected hashes, in first-recorded order; `None` for nodes without a local hash.
pub fn expected_graph_identity_hashes(graph: &IdentityGraph) -> IdentityHashes {
    let mut resolver = IdentityResolver::new(&graph.nodes, None, Vec::new());
    for key in &graph.execution_order {
        let _ = resolver.resolve_expected(key);
    }
    resolver.into_hashes()
}
