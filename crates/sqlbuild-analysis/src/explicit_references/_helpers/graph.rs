//! Python's lineage upstream edges and transitive closure over compiled resource keys.

use std::collections::HashMap;

use sqlbuild_core::graph_walk::main::breadth_first_path::breadth_first_path;

use crate::explicit_references::constants::SQL_TEST_TYPE;
use crate::explicit_references::models::GraphResource;
use crate::explicit_references::types::ResourceKey;

/// Upstream keys per resource key.
pub(crate) type Upstream = HashMap<ResourceKey, Vec<ResourceKey>>;

/// `build_lineage_upstream_deps_impl`: each resource's dependencies without SQL tests.
pub(crate) fn lineage_upstream(resources: &[GraphResource]) -> Upstream {
    let mut upstream: Upstream = HashMap::new();
    for resource in resources {
        if resource.key.0 == SQL_TEST_TYPE {
            continue;
        }
        upstream.insert(
            resource.key.clone(),
            resource
                .deps
                .iter()
                .filter(|dep| dep.0 != SQL_TEST_TYPE)
                .cloned()
                .collect(),
        );
    }
    upstream
}

/// Whether `target` is reachable from `start` over at least one upstream edge.
pub(crate) fn reaches(upstream: &Upstream, start: &ResourceKey, target: &ResourceKey) -> bool {
    breadth_first_path(
        start,
        (
            |current: &&ResourceKey| upstream.get(*current).into_iter().flatten(),
            |neighbour: &&ResourceKey| *neighbour == target,
            |_: &&ResourceKey| true,
        ),
    )
    .is_some()
}
