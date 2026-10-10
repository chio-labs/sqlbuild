//! Python's lineage upstream edges and transitive closure over compiled resource keys.

use std::collections::{HashMap, HashSet, VecDeque};

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
    let mut visited: HashSet<&ResourceKey> = HashSet::new();
    let mut frontier: VecDeque<&ResourceKey> = VecDeque::from([start]);
    while let Some(current) = frontier.pop_front() {
        for neighbor in upstream.get(current).into_iter().flatten() {
            if visited.insert(neighbor) {
                if neighbor == target {
                    return true;
                }
                frontier.push_back(neighbor);
            }
        }
    }
    false
}
