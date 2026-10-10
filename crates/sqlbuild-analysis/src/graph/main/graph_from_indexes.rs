use crate::graph::models::{GraphIndexes, ProjectGraph};

/// A graph over indexes the caller built, keeping their order.
pub fn graph_from_indexes(indexes: GraphIndexes) -> ProjectGraph {
    crate::graph::_helpers::indexes::from_indexes(indexes)
}
