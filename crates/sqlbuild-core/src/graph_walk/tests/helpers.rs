use std::collections::HashMap;

use crate::graph_walk::main::kahn_order::kahn_order;
use crate::graph_walk::models::VisitOrder;
use crate::graph_walk::tests::test_types::KahnTestCase;
use crate::graph_walk::types::{NodeSet, ReadyQueue};

/// Adjacency from `(node, neighbours)` rows.
pub(super) fn adjacency(
    rows: &[(&'static str, &[&'static str])],
) -> HashMap<&'static str, Vec<&'static str>> {
    rows.iter()
        .map(|(node, neighbours)| (*node, neighbours.to_vec()))
        .collect()
}

/// The neighbours of `node`, none when it has no row.
pub(super) fn neighbours(
    edges: &HashMap<&'static str, Vec<&'static str>>,
    node: &'static str,
) -> Vec<&'static str> {
    edges.get(node).cloned().unwrap_or_default()
}

/// `edges` reversed, each parent list in row order.
pub(super) fn inverted(
    rows: &[(&'static str, &[&'static str])],
) -> HashMap<&'static str, Vec<&'static str>> {
    let mut parents: HashMap<&'static str, Vec<&'static str>> = HashMap::new();
    for (node, children) in rows {
        for child in *children {
            parents.entry(*child).or_default().push(*node);
        }
    }
    parents
}

/// A visit order holding `starts` when they are included.
pub(super) fn recorded_starts(starts: &[&'static str], include: bool) -> VisitOrder<&'static str> {
    let mut visited: VisitOrder<&'static str> = VisitOrder::default();
    for start in starts.iter().filter(|_| include) {
        let Ok(_) = visited.insert_new(start);
    }
    visited
}

/// The Kahn order of one test case under `ready`, counting every edge.
pub(super) fn kahn_case_order<Q: ReadyQueue<&'static str>>(
    test_case: &KahnTestCase,
    ready: Q,
) -> Vec<&'static str> {
    let edges = adjacency(test_case.edges);
    let mut remaining: HashMap<&'static str, usize> =
        test_case.nodes.iter().map(|node| (*node, 0)).collect();
    for (_, successors) in test_case.edges {
        for successor in *successors {
            *remaining.entry(successor).or_default() += 1;
        }
    }
    kahn_order(
        (test_case.nodes.iter().copied(), remaining),
        ready,
        |node: &&'static str| neighbours(&edges, node),
    )
}
