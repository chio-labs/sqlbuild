//! Resolve SQLBuild selectors over a DAG artifact into the selected node ids.

use std::collections::{BTreeMap, BTreeSet};

use crate::dag_artifact::_helpers::selection::{Adjacency, resolve_expression};
use crate::dag_artifact::errors::DagSelectionError;
use crate::dag_artifact::models::{DagSelectionGraph, DagSelectionIndex, DagSelectionNode};

/// Node ids `select` matches minus those `exclude` matches.
pub fn resolve_dag_selection(
    graph: &DagSelectionGraph,
    (select, exclude): (&str, Option<&str>),
) -> Result<BTreeSet<String>, DagSelectionError> {
    let mut nodes: BTreeMap<&str, &DagSelectionNode> = BTreeMap::new();
    for node in &graph.nodes {
        nodes.insert(node.id.as_str(), node);
    }
    let mut upstream: Adjacency = Adjacency::new();
    let mut downstream: Adjacency = Adjacency::new();
    for id in nodes.keys() {
        upstream.insert((*id).to_owned(), BTreeSet::new());
        downstream.insert((*id).to_owned(), BTreeSet::new());
    }
    for (from_id, to_id) in &graph.edges {
        if !nodes.contains_key(from_id.as_str()) || !nodes.contains_key(to_id.as_str()) {
            continue;
        }
        upstream
            .entry(to_id.clone())
            .or_default()
            .insert(from_id.clone());
        downstream
            .entry(from_id.clone())
            .or_default()
            .insert(to_id.clone());
    }
    let index: DagSelectionIndex<'_> = DagSelectionIndex {
        graph,
        nodes,
        upstream,
        downstream,
    };
    let mut selected: BTreeSet<String> = resolve_expression(&index, select)?;
    if let Some(exclude) = exclude.filter(|exclude| !exclude.is_empty()) {
        for excluded in resolve_expression(&index, exclude)? {
            selected.remove(&excluded);
        }
    }
    Ok(selected)
}
