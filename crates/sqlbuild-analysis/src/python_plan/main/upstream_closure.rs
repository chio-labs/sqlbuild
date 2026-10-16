//! Every node upstream of one Python node, sorted.

use std::collections::{HashMap, HashSet};
use std::convert::Infallible;

use sqlbuild_core::graph_walk::main::breadth_first_reach::breadth_first_reach;

/// `sorted(transitive_closure(start=start, edges=upstream))`: `start` only when on a cycle.
pub fn upstream_closure(start: &str, upstream: &HashMap<String, Vec<String>>) -> Vec<String> {
    let mut visited: HashSet<&str> = HashSet::new();
    let Ok(()) = breadth_first_reach([start], None, &mut visited, |current| {
        Ok::<_, Infallible>(
            upstream
                .get(*current)
                .into_iter()
                .flatten()
                .map(String::as_str),
        )
    });
    let mut names: Vec<String> = visited.into_iter().map(str::to_owned).collect();
    names.sort();
    names
}
