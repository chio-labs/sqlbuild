//! One selector term at a time: path selectors, SQLBuild selectors and dbt anchors.

use std::collections::HashSet;

use crate::dbt_graph::_helpers::closure::{path_nodes, reachable};
use crate::dbt_graph::_helpers::endpoints::{endpoint_key, endpoint_names};
use crate::dbt_graph::constants::PATH_SELECTOR_SEPARATOR;
use crate::dbt_graph::errors::DbtSelectionError;
use crate::dbt_graph::models::{
    DbtCombinedGraph, DbtGraphKey, DbtGraphOwner, DbtSelection, DbtSelectionRequest,
    DbtSelectionState, DbtSelectorExpansion,
};
use crate::dbt_graph::types::DbtSelectorResolver;

fn added(
    mut state: DbtSelectionState,
    keys: impl IntoIterator<Item = DbtGraphKey>,
) -> DbtSelectionState {
    for key in keys {
        match key.owner {
            DbtGraphOwner::Sqlbuild => state.sqlbuild.insert(key.name),
            DbtGraphOwner::Dbt => state.dbt.insert(key.name),
        };
    }
    state
}

fn expanded(
    keys: HashSet<DbtGraphKey>,
    parsed: &DbtSelectorExpansion,
    graph: &DbtCombinedGraph,
) -> HashSet<DbtGraphKey> {
    let mut result: HashSet<DbtGraphKey> = keys.clone();
    if parsed.upstream {
        for key in &keys {
            result.extend(reachable(key, &graph.upstream));
        }
    }
    if parsed.downstream {
        for key in &keys {
            result.extend(reachable(key, &graph.downstream));
        }
    }
    result
}

fn path_keys<E>(
    resolver: &impl DbtSelectorResolver<Error = E>,
    (graph, request): (&DbtCombinedGraph, &DbtSelectionRequest<'_>),
    (core, raw_term): (&str, &str),
) -> Result<HashSet<DbtGraphKey>, DbtSelectionError<E>> {
    let (start_name, end_name) = endpoint_names(core, raw_term)?;
    let start: DbtGraphKey =
        endpoint_key(resolver, request.manifest_models, (start_name, raw_term))?;
    let end: DbtGraphKey = endpoint_key(resolver, request.manifest_models, (end_name, raw_term))?;
    Ok(path_nodes((&start, &end), &graph.downstream, &graph.upstream).unwrap_or_default())
}

fn with_anchor(mut selection: DbtSelection, term: &str, unique_ids: &[String]) -> DbtSelection {
    selection.dbt_anchor_terms.push(term.to_owned());
    match selection
        .dbt_anchor_unique_ids_by_term
        .iter_mut()
        .find(|(existing, _)| existing == term)
    {
        Some((_, existing)) => unique_ids.clone_into(existing),
        None => selection
            .dbt_anchor_unique_ids_by_term
            .push((term.to_owned(), unique_ids.to_vec())),
    }
    selection
}

fn anchored(
    mut state: DbtSelectionState,
    (graph, request): (&DbtCombinedGraph, &DbtSelectionRequest<'_>),
    term: &str,
) -> DbtSelectionState {
    let anchors: &[String] = request
        .anchor_unique_ids_by_term
        .get(term)
        .map_or(&[], Vec::as_slice);
    state.selection = with_anchor(state.selection, term, anchors);
    for unique_id in anchors {
        state = added(
            state,
            reachable(&DbtGraphKey::dbt_model(unique_id), &graph.downstream),
        );
    }
    state
}

/// `state` with one select term resolved into it.
pub(crate) fn select_term<E>(
    resolver: &impl DbtSelectorResolver<Error = E>,
    inputs: (&DbtCombinedGraph, &DbtSelectionRequest<'_>),
    term: &str,
    state: DbtSelectionState,
) -> Result<DbtSelectionState, DbtSelectionError<E>> {
    let graph: &DbtCombinedGraph = inputs.0;
    let parsed: DbtSelectorExpansion = resolver.split(term).map_err(DbtSelectionError::Resolver)?;
    if parsed.core.contains(PATH_SELECTOR_SEPARATOR) {
        let keys: HashSet<DbtGraphKey> = path_keys(resolver, inputs, (&parsed.core, term))?;
        return Ok(added(state, expanded(keys, &parsed, graph)));
    }
    let (names, translated_path) = resolver
        .model_names(&parsed.core)
        .map_err(DbtSelectionError::Resolver)?;
    let mut state: DbtSelectionState = state;
    if let Some(translated_path) = translated_path {
        state
            .selection
            .path_translations
            .push((term.to_owned(), translated_path));
    }
    if !names.is_empty() {
        let keys: HashSet<DbtGraphKey> = names
            .iter()
            .map(|name| DbtGraphKey::sqlbuild_model(name))
            .collect();
        return Ok(added(state, expanded(keys, &parsed, graph)));
    }
    if !parsed.downstream {
        return Ok(state);
    }
    Ok(anchored(state, inputs, term))
}

/// The final selection: sorted names without excluded SQLBuild models.
pub(crate) fn finished<E>(
    resolver: &impl DbtSelectorResolver<Error = E>,
    exclude: &[String],
    state: DbtSelectionState,
) -> Result<DbtSelection, E> {
    let mut excluded: HashSet<String> = HashSet::new();
    for term in exclude {
        let parsed: DbtSelectorExpansion = resolver.split(term)?;
        excluded.extend(resolver.model_names(&parsed.core)?.0);
    }
    let mut selection: DbtSelection = state.selection;
    selection.sqlbuild_model_names = state
        .sqlbuild
        .into_iter()
        .filter(|name| !excluded.contains(name))
        .collect();
    selection.dbt_required_unique_ids = state.dbt.into_iter().collect();
    Ok(selection)
}
