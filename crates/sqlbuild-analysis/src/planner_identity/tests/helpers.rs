use std::collections::{HashMap, HashSet};

use crate::planner_identity::_helpers::compose_graph_identity::compose_graph_identity;
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

/// A chain where each model reads the previous one, resolved from its most downstream model.
pub(super) fn chain_identity_graph(depth: usize) -> IdentityGraph {
    let mut graph = IdentityGraph::default();
    for index in 0..depth {
        let upstream_keys: Vec<GraphKey> = index
            .checked_sub(1)
            .map(|upstream| model(&format!("m{upstream}")))
            .into_iter()
            .collect();
        graph.nodes.insert(
            model(&format!("m{index}")),
            IdentityNode {
                upstream_keys,
                local_hash: Some(format!("local_m{index}")),
            },
        );
    }
    graph.execution_order = (0..depth)
        .rev()
        .map(|index| model(&format!("m{index}")))
        .collect();
    graph
}

/// The most downstream hash of `chain_identity_graph`, composed one link at a time.
pub(super) fn chain_head_hash(depth: usize) -> Option<String> {
    let mut hash: Option<String> = None;
    for index in 0..depth {
        let upstream: Vec<&str> = hash.iter().map(String::as_str).collect();
        hash = Some(compose_graph_identity(
            &format!("local_m{index}"),
            &upstream,
        ));
    }
    hash
}

/// The staleness graph of a model chain whose most upstream model changed outside the run set.
pub(super) fn chain_staleness_graph(depth: usize) -> StalenessGraph {
    let head: String = format!("m{}", depth - 1);
    let mut graph = StalenessGraph {
        upstream_deps: (1..depth)
            .map(|index| {
                (
                    model(&format!("m{index}")),
                    vec![model(&format!("m{}", index - 1))],
                )
            })
            .collect(),
        selected_model_names: vec![head.clone()],
        ..StalenessGraph::default()
    };
    graph.changed.models = names(&["m0"]);
    graph.run.models = HashSet::from([head]);
    graph
}
