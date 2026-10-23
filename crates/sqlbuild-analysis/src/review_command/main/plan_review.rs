//! What a review builds: the changed set, its downstream under the policy, and `--select`.

use std::collections::BTreeSet;

use crate::review_command::_helpers::scope::{
    ReviewScope, in_order, required_upstream, review_scope, selected_scope, split_affected,
};
use crate::review_command::errors::ReviewPlanError;
use crate::review_command::models::{
    AddedNode, ChangedNode, DownstreamPolicy, ReviewGraph, ReviewPlan, SelectedToken,
};

/// Plan a review of `changed` over `graph`; `select` tokens intersect with the planned scope.
pub fn plan_review(
    graph: &ReviewGraph,
    changed: &[ChangedNode],
    policy: DownstreamPolicy,
    select: Option<&[SelectedToken]>,
) -> Result<ReviewPlan, ReviewPlanError> {
    let scope: ReviewScope = review_scope(graph, changed, policy);
    let mut validated_set: BTreeSet<String> = selected_scope((graph, policy), &scope, select)?;
    let added: Vec<AddedNode> = required_upstream(graph, &validated_set, &scope.rebuildable);
    validated_set.extend(added.iter().map(|node| node.name.clone()));
    let (validated, not_validated) = split_affected((graph, policy), &scope, &validated_set);
    let hooked: BTreeSet<String> = validated_set
        .iter()
        .filter(|name| graph.nodes.get(*name).is_some_and(|node| node.has_hooks))
        .cloned()
        .collect();
    Ok(ReviewPlan {
        policy,
        changed: changed.to_vec(),
        validated,
        not_validated,
        critical: in_order(graph, &scope.critical),
        added,
        hooks: in_order(graph, &hooked),
    })
}
