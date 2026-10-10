use crate::assembly::project::types::ObjectKey;
use crate::graph::_helpers::selectors::Keys;
use crate::graph::models::{BuildResources, ProjectGraph};

/// The selected keys plus the functions and seeds Python adds to build them, sorted.
pub fn build_resources(
    graph: &ProjectGraph,
    selected: &[ObjectKey],
    include: BuildResources,
) -> Vec<ObjectKey> {
    let selected: Keys = selected.iter().cloned().collect();
    crate::graph::_helpers::selectors::build_resources(graph, &selected, include)
        .into_iter()
        .collect()
}
