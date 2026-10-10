use crate::graph::models::{GraphResource, ProjectGraph};

/// The graph indexes Python builds from a compiled project's models, sources, seeds and functions.
pub fn build_project_graph(resources: &[GraphResource]) -> ProjectGraph {
    crate::graph::_helpers::indexes::build(resources)
}
