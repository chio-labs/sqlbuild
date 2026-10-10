use crate::graph::models::ProjectGraph;

/// How many execution layers the compile report counts over the project's models.
pub fn model_layer_count(graph: &ProjectGraph) -> usize {
    crate::graph::_helpers::layers::model_layer_count(graph)
}
