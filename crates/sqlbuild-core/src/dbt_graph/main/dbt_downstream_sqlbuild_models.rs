//! SQLBuild models downstream of dbt models.

use crate::graph_walk::main::breadth_first_reach::breadth_first_reach;
use std::collections::{BTreeSet, HashSet};
use std::convert::Infallible;

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
        let start: DbtGraphKey = DbtGraphKey::dbt_model(unique_id);
        let mut reached: HashSet<&DbtGraphKey> = HashSet::new();
        let Ok(()) = breadth_first_reach([&start], None, &mut reached, |key| {
            Ok::<_, Infallible>(graph.downstream.targets.get(*key).into_iter().flatten())
        });
        for key in reached {
            if key.owner == DbtGraphOwner::Sqlbuild
                && key.resource_type == DbtGraphResourceType::Model
            {
                names.insert(key.name.clone());
            }
        }
    }
    names.into_iter().collect()
}
