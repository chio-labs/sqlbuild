//! The asset nodes an orchestrator definition owns and their dependencies.

use std::collections::HashMap;

use crate::dag_artifact::_helpers::projection::{nodes_by_id, upstream_by_id};
use crate::dag_artifact::models::{AssetNodePlan, AssetProjectionPolicy, DagProjectionGraph};

/// Each node of an asset kind, in artifact order, with its upstream nodes in edge order.
#[must_use]
pub fn dag_asset_plans(
    graph: &DagProjectionGraph,
    policy: &AssetProjectionPolicy,
) -> Vec<AssetNodePlan> {
    let nodes: HashMap<&str, usize> = nodes_by_id(graph);
    let upstream: HashMap<&str, Vec<&str>> = upstream_by_id(graph);
    let is_asset = |index: usize| policy.asset_kinds.contains(&graph.nodes[index].kind);
    let mut plans: Vec<AssetNodePlan> = Vec::new();
    for (index, node) in graph.nodes.iter().enumerate() {
        if !is_asset(index) {
            continue;
        }
        let mut dependencies: Vec<usize> = Vec::new();
        for upstream_id in upstream.get(node.id.as_str()).into_iter().flatten() {
            match nodes.get(upstream_id) {
                Some(dependency) if !policy.upstream_asset_kinds_only || is_asset(*dependency) => {
                    dependencies.push(*dependency);
                }
                _ => {}
            }
        }
        plans.push(AssetNodePlan {
            node: index,
            upstream: dependencies,
        });
    }
    plans
}
