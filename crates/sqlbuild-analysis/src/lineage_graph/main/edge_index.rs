//! Edge indexes for the project column lineage graph.

use std::collections::HashMap;

use crate::lineage_graph::models::{EdgeIndex, EdgeKey};

/// Index `edges` by target model and source resource; equal edges share their first position.
pub fn edge_index(edges: &[EdgeKey]) -> EdgeIndex {
    let mut index = EdgeIndex {
        first_equal: Vec::with_capacity(edges.len()),
        ..EdgeIndex::default()
    };
    let mut first_positions: HashMap<&EdgeKey, usize> = HashMap::with_capacity(edges.len());
    for (position, edge) in edges.iter().enumerate() {
        index
            .by_target_model
            .entry(edge.target_model.clone())
            .or_default()
            .push(position);
        index
            .by_source_resource
            .entry(edge.source_name.clone())
            .or_default()
            .push(position);
        index
            .first_equal
            .push(*first_positions.entry(edge).or_insert(position));
    }
    index
}
