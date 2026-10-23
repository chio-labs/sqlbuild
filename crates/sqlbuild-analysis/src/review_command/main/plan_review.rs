//! What a review builds: the changed set, its downstream under the policy, and `--select`.

use std::collections::BTreeSet;

use crate::review_command::_helpers::graph::descendants;
use crate::review_command::_helpers::scope::{
    check_token, not_validated_reason, policy_downstream,
};
use crate::review_command::errors::ReviewPlanError;
use crate::review_command::models::{
    ChangedNode, DownstreamPolicy, NotValidated, ReviewGraph, ReviewPlan, SelectedToken,
};

/// Plan a review of `changed` over `graph`; `select` tokens intersect with the planned scope.
pub fn plan_review(
    graph: &ReviewGraph,
    changed: &[ChangedNode],
    policy: DownstreamPolicy,
    select: Option<&[SelectedToken]>,
) -> Result<ReviewPlan, ReviewPlanError> {
    let changed_names: BTreeSet<String> = changed
        .iter()
        .filter(|node| graph.nodes.contains_key(&node.name))
        .map(|node| node.name.clone())
        .collect();
    let downstream: BTreeSet<String> = descendants(graph, &changed_names)
        .into_iter()
        .filter(|name| !changed_names.contains(name))
        .collect();
    let affected: BTreeSet<String> = changed_names.union(&downstream).cloned().collect();
    let critical: BTreeSet<String> = affected
        .iter()
        .filter(|name| graph.nodes.get(*name).is_some_and(|node| node.critical))
        .cloned()
        .collect();
    let mut scope: BTreeSet<String> = changed_names.clone();
    scope.extend(policy_downstream(
        graph,
        policy,
        (&changed_names, &downstream),
        &critical,
    ));
    let validated_set: BTreeSet<String> = match select {
        None => scope.clone(),
        Some(tokens) => {
            let mut selected: BTreeSet<String> = BTreeSet::new();
            for token in tokens {
                check_token(token, (graph, policy), (&affected, &scope))?;
                selected.extend(token.names.iter().cloned());
            }
            scope.intersection(&selected).cloned().collect()
        }
    };
    let mut validated: Vec<String> = Vec::new();
    let mut not_validated: Vec<NotValidated> = Vec::new();
    for name in &graph.order {
        if validated_set.contains(name) {
            validated.push(name.clone());
        } else if affected.contains(name) {
            not_validated.push(NotValidated {
                name: name.clone(),
                reason: not_validated_reason(name, (&changed_names, &scope), policy),
            });
        }
    }
    Ok(ReviewPlan {
        policy,
        changed: changed.to_vec(),
        validated,
        not_validated,
        critical: graph
            .order
            .iter()
            .filter(|name| critical.contains(*name))
            .cloned()
            .collect(),
    })
}
