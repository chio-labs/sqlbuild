use crate::graph::errors::SelectorError;
use crate::python_selection::_helpers::nodes::select_nodes;
use crate::python_selection::models::{NodeIndex, PythonSelectionGraph};

/// The Python node names `select` minus `exclude` resolve to, sorted; every node when unselected.
pub fn resolve_python_node_selectors(
    graph: &PythonSelectionGraph,
    select: &[String],
    exclude: &[String],
) -> Result<Vec<String>, SelectorError> {
    Ok(select_nodes(&NodeIndex::new(graph), select, exclude)?
        .into_iter()
        .collect())
}
