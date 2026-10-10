use crate::assembly::project::types::ObjectKey;
use crate::graph::models::{EdgeDirection, ProjectGraph};

/// A key's direct lineage neighbours in graph order; empty for a key the graph does not hold.
pub fn edge_keys<'graph>(
    graph: &'graph ProjectGraph,
    key: &ObjectKey,
    direction: EdgeDirection,
) -> &'graph [ObjectKey] {
    graph.edges(key, direction)
}
