//! Resolve `sqb dbt` selectors to SQLBuild models and the dbt nodes they require.

use crate::dbt_graph::_helpers::selection::{finished, select_term};
use crate::dbt_graph::errors::DbtSelectionError;
use crate::dbt_graph::models::{
    DbtCombinedGraph, DbtSelection, DbtSelectionRequest, DbtSelectionState,
};
use crate::dbt_graph::types::DbtSelectorResolver;

/// Resolve each term in order: path selectors, SQLBuild selectors, then trailing-plus dbt anchors.
pub fn resolve_dbt_selection<E>(
    resolver: &impl DbtSelectorResolver<Error = E>,
    graph: &DbtCombinedGraph,
    request: &DbtSelectionRequest<'_>,
) -> Result<DbtSelection, DbtSelectionError<E>> {
    let mut state: DbtSelectionState = DbtSelectionState::default();
    for term in request.select {
        state = select_term(resolver, (graph, request), term, state)?;
    }
    finished(resolver, request.exclude, state).map_err(DbtSelectionError::Resolver)
}
