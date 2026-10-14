use std::collections::{HashMap, HashSet};

use crate::planner_identity::models::{GraphKey, IdentityGraph, IdentityNode, StalenessGraph};

pub(super) fn key(kind: &str, name: &str) -> GraphKey {
    GraphKey {
        kind: kind.to_owned(),
        name: name.to_owned(),
    }
}

pub(super) fn model(name: &str) -> GraphKey {
    key("model", name)
}

pub(super) fn names(values: &[&str]) -> HashSet<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

pub(super) fn texts(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// Nodes `a`, `b` over `a`, `c` over `a`, `b` and unknown `x`, and `d` over `c` without a local hash.
pub(super) fn identity_graph() -> IdentityGraph {
    let node = |upstream: &[&str], local: Option<&str>| IdentityNode {
        upstream_keys: upstream.iter().map(|name| model(name)).collect(),
        local_hash: local.map(str::to_owned),
    };
    IdentityGraph {
        nodes: HashMap::from([
            (model("a"), node(&[], Some("la"))),
            (model("b"), node(&["a"], Some("lb"))),
            (model("c"), node(&["a", "b", "x"], Some("lc"))),
            (model("d"), node(&["c"], None)),
        ]),
        execution_order: vec![model("c"), model("a"), model("b"), model("d")],
    }
}

pub(super) fn staleness_graph(
    edges: &[(GraphKey, &[GraphKey])],
    selected: &[&str],
) -> StalenessGraph {
    StalenessGraph {
        upstream_deps: edges
            .iter()
            .map(|(node, upstream)| (node.clone(), upstream.to_vec()))
            .collect(),
        selected_model_names: texts(selected),
        ..StalenessGraph::default()
    }
}

/// Two models reading each other.
pub(super) fn cyclic_identity_graph() -> IdentityGraph {
    let node = |upstream: &str, local: &str| IdentityNode {
        upstream_keys: vec![model(upstream)],
        local_hash: Some(local.to_owned()),
    };
    IdentityGraph {
        nodes: HashMap::from([(model("a"), node("b", "la")), (model("b"), node("a", "lb"))]),
        execution_order: vec![model("a"), model("b")],
    }
}

/// A dense ladder: each layer's two nodes read both nodes of the previous layer.
pub(super) fn ladder_identity_graph(layer_count: usize) -> IdentityGraph {
    let mut graph = IdentityGraph::default();
    let mut previous: Vec<GraphKey> = Vec::new();
    for layer in 0..layer_count {
        let current: Vec<GraphKey> = ["a", "b"]
            .iter()
            .map(|suffix| model(&format!("L{layer}_{suffix}")))
            .collect();
        for key in &current {
            graph.nodes.insert(
                key.clone(),
                IdentityNode {
                    upstream_keys: previous.clone(),
                    local_hash: Some(format!("local_{}", key.name)),
                },
            );
            graph.execution_order.push(key.clone());
        }
        previous = current;
    }
    graph
}
