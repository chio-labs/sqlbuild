//! The checks an orchestrator check definition exposes and the nodes they check.

use std::collections::HashMap;

use crate::dag_artifact::_helpers::projection::nodes_by_id;
use crate::dag_artifact::models::{
    CheckKindFilter, CheckPlan, DagProjectionCheck, DagProjectionGraph,
};

/// Whether `filter` exposes checks of `kind`.
fn exposed(filter: &CheckKindFilter, kind: &str) -> bool {
    !filter.excluded.contains(kind)
        && filter
            .required
            .as_ref()
            .is_none_or(|required| required.contains(kind))
}

/// The indexes of the known nodes `check` names, in its order.
fn checked_nodes(nodes: &HashMap<&str, usize>, check: &DagProjectionCheck) -> Vec<usize> {
    check
        .checked_asset_ids
        .iter()
        .filter_map(|id| nodes.get(id.as_str()).copied())
        .collect()
}

/// Every check in artifact order, whether `filter` exposes its kind, and its known checked nodes.
#[must_use]
pub fn dag_check_plans(graph: &DagProjectionGraph, filter: &CheckKindFilter) -> Vec<CheckPlan> {
    let nodes: HashMap<&str, usize> = nodes_by_id(graph);
    graph
        .checks
        .iter()
        .enumerate()
        .map(|(index, check)| CheckPlan {
            check: index,
            included: exposed(filter, &check.kind),
            nodes: checked_nodes(&nodes, check),
        })
        .collect()
}
