//! SQLBuild models downstream of dbt models.

use std::collections::BTreeSet;

use crate::dbt_graph::_helpers::closure::reachable;
use crate::dbt_graph::models::{
    DbtCombinedGraph, DbtGraphKey, DbtGraphOwner, DbtGraphResourceType,
};

/// Sorted names of SQLBuild models transitively downstream of any of the dbt models.
#[must_use]
pub fn dbt_downstream_sqlbuild_models(
    graph: &DbtCombinedGraph,
    unique_ids: &[String],
) -> Vec<String> {
    let mut names: BTreeSet<String> = BTreeSet::new();
    for unique_id in unique_ids {
        for key in reachable(&DbtGraphKey::dbt_model(unique_id), &graph.downstream) {
            if key.owner == DbtGraphOwner::Sqlbuild
                && key.resource_type == DbtGraphResourceType::Model
            {
                names.insert(key.name);
            }
        }
    }
    names.into_iter().collect()
}
