//! The scope a downstream policy plans, and the checks on `--select` tokens.

use std::collections::BTreeSet;

use crate::review_command::_helpers::graph::ancestors_within;
use crate::review_command::_helpers::wording::policy_name;
use crate::review_command::constants::{
    OUT_OF_SCOPE_SELECTION_CODE, UNCHANGED_SELECTION_CODE, UNKNOWN_SELECTION_CODE,
};
use crate::review_command::errors::ReviewPlanError;
use crate::review_command::models::{DownstreamPolicy, ReviewGraph, SelectedToken};

fn selection_error(code: &str, message: String, help: &str) -> ReviewPlanError {
    ReviewPlanError {
        code: code.to_owned(),
        message,
        help: Some(help.to_owned()),
    }
}

/// The downstream nodes the policy validates.
pub(crate) fn policy_downstream(
    graph: &ReviewGraph,
    policy: DownstreamPolicy,
    (changed, downstream): (&BTreeSet<String>, &BTreeSet<String>),
    critical: &BTreeSet<String>,
) -> BTreeSet<String> {
    match policy {
        DownstreamPolicy::None => BTreeSet::new(),
        DownstreamPolicy::All => downstream.clone(),
        DownstreamPolicy::Critical => {
            let reachable: BTreeSet<String> = changed.union(downstream).cloned().collect();
            ancestors_within(graph, critical, &reachable)
                .into_iter()
                .filter(|name| downstream.contains(name))
                .collect()
        }
    }
}

/// Reject a token that matches nothing, only unchanged nodes, or only nodes outside the policy.
pub(crate) fn check_token(
    token: &SelectedToken,
    (graph, policy): (&ReviewGraph, DownstreamPolicy),
    (affected, scope): (&BTreeSet<String>, &BTreeSet<String>),
) -> Result<(), ReviewPlanError> {
    let known: Vec<&String> = token
        .names
        .iter()
        .filter(|name| graph.nodes.contains_key(*name))
        .collect();
    if known.is_empty() {
        return Err(selection_error(
            UNKNOWN_SELECTION_CODE,
            format!("--select {} matches no model or seed", token.token),
            "select a changed model or seed by name, or a selector such as stg_orders+",
        ));
    }
    if known.iter().any(|name| scope.contains(*name)) {
        return Ok(());
    }
    if known.iter().any(|name| affected.contains(*name)) {
        return Err(selection_error(
            OUT_OF_SCOPE_SELECTION_CODE,
            format!(
                "--select {} matches only downstream nodes that --downstream {} leaves out",
                token.token,
                policy_name(policy)
            ),
            "pass --downstream all to review every downstream node",
        ));
    }
    Err(selection_error(
        UNCHANGED_SELECTION_CODE,
        format!(
            "--select {} matches only nodes that did not change and are not downstream of a change",
            token.token
        ),
        "a review validates changed nodes and their downstream; run sqb build for other nodes",
    ))
}

/// Why an affected node is left out of the review.
pub(crate) fn not_validated_reason(
    name: &str,
    (changed, scope): (&BTreeSet<String>, &BTreeSet<String>),
    policy: DownstreamPolicy,
) -> String {
    if changed.contains(name) || scope.contains(name) {
        return "not selected (--select)".to_owned();
    }
    match policy {
        DownstreamPolicy::Critical => {
            "not on a path to a critical model (--downstream critical)".to_owned()
        }
        DownstreamPolicy::All | DownstreamPolicy::None => {
            "downstream of a change (--downstream none)".to_owned()
        }
    }
}
