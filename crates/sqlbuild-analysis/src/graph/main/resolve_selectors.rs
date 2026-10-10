use crate::assembly::project::types::ObjectKey;
use crate::graph::models::{ProjectGraph, SelectorError};

/// The keys `--select` minus `--exclude` resolve to, with their build functions, sorted.
pub fn resolve_selectors(
    graph: &ProjectGraph,
    select: &[String],
    exclude: &[String],
) -> Result<Vec<ObjectKey>, SelectorError> {
    crate::graph::_helpers::selectors::resolve(graph, select, exclude)
}
