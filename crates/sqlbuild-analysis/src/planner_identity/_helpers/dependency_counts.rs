//! Kahn's algorithm inputs: every key, each key's upstream count and its downstream keys.

use std::collections::{HashMap, HashSet};

use crate::planner_identity::models::GraphKey;

/// Every key named in the edges, its number of upstream entries and its downstream keys, one per edge.
pub(crate) struct DependencyCounts<'a> {
    pub(crate) node_keys: HashSet<&'a GraphKey>,
    pub(crate) indegree: HashMap<&'a GraphKey, usize>,
    pub(crate) downstream: HashMap<&'a GraphKey, Vec<&'a GraphKey>>,
}

/// The counts of `upstream`, counting repeated upstream entries once per entry.
pub(crate) fn dependency_counts(upstream: &[(GraphKey, Vec<GraphKey>)]) -> DependencyCounts<'_> {
    let mut counts = DependencyCounts {
        node_keys: HashSet::new(),
        indegree: HashMap::new(),
        downstream: HashMap::new(),
    };
    for (key, dep_keys) in upstream {
        counts.node_keys.insert(key);
        for dep_key in dep_keys {
            counts.node_keys.insert(dep_key);
            counts.downstream.entry(dep_key).or_default().push(key);
        }
    }
    for key in &counts.node_keys {
        counts.indegree.insert(key, 0);
    }
    for (key, dep_keys) in upstream {
        counts.indegree.insert(key, dep_keys.len());
    }
    counts
}
