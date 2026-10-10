use crate::assembly::project::types::ObjectKey;
use crate::graph::errors::SelectorError;
use crate::graph::models::ProjectGraph;

/// Python's `match_selector_keys`: the keys a `kind:value` selector names before `+` expansion.
pub fn match_selector(
    graph: &ProjectGraph,
    kind: &str,
    value: &str,
) -> Result<Vec<ObjectKey>, SelectorError> {
    crate::graph::_helpers::selectors::matched(graph, kind, value)
        .map(|keys| keys.into_iter().collect())
}
