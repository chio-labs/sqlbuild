//! Stable depth-first ordering for migration identity propagation.

use std::collections::BTreeMap;

use sqlbuild_core::graph_walk::main::depth_first_postorder::depth_first_postorder;

/// Order models after their model dependencies using lexical traversal ties.
pub fn discovery_order(dependencies: &BTreeMap<String, Vec<String>>) -> Vec<String> {
    depth_first_postorder(dependencies.keys().cloned(), |name| {
        let mut upstream: Vec<String> = dependencies[name]
            .iter()
            .filter(|dependency| dependencies.contains_key(*dependency))
            .cloned()
            .collect();
        upstream.sort();
        upstream
    })
}
