//! The selected nodes an orchestrator owns as assets.

use std::collections::BTreeSet;

use crate::dag_artifact::models::DagProjectionGraph;

/// Indexes of nodes whose id is selected and whose kind is an asset kind, in artifact order.
#[must_use]
pub fn dag_selected_asset_nodes(
    graph: &DagProjectionGraph,
    selected_ids: &BTreeSet<String>,
    asset_kinds: &BTreeSet<String>,
) -> Vec<usize> {
    graph
        .nodes
        .iter()
        .enumerate()
        .filter(|(_, node)| selected_ids.contains(&node.id) && asset_kinds.contains(&node.kind))
        .map(|(index, _)| index)
        .collect()
}
