use crate::assembly::project::types::ObjectKey;
use crate::graph::errors::SelectorError;
use crate::graph::models::ProjectGraph;

/// The keys whitespace-separated selector tokens match, without build resources, sorted.
pub fn resolve_selector_tokens(
    graph: &ProjectGraph,
    selectors: &[String],
) -> Result<Vec<ObjectKey>, SelectorError> {
    crate::graph::_helpers::selectors::tokens(graph, selectors)
        .map(|keys| keys.into_iter().collect())
}
