use crate::python_selection::models::{InventoryIndexes, InventoryNode};

/// Python's `PythonNodeGraph` edges, adjacency, tag and path indexes for discovered nodes.
pub fn python_node_graph_indexes(nodes: &[InventoryNode]) -> InventoryIndexes {
    crate::python_selection::_helpers::inventory::indexes(nodes)
}
