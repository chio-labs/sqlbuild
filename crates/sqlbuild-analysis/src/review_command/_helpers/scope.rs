//! The scope a downstream policy plans, the nodes a review cannot rebuild, and `--select` checks.

use std::collections::{BTreeMap, BTreeSet};

use crate::review_command::_helpers::graph::{ancestors_within, descendants, upstream_of};
use crate::review_command::_helpers::wording::policy_name;
use crate::review_command::constants::{
    OUT_OF_SCOPE_SELECTION_CODE, UNCHANGED_SELECTION_CODE, UNKNOWN_SELECTION_CODE,
};
use crate::review_command::errors::ReviewPlanError;
use crate::review_command::models::{
    AddedNode, ChangedNode, DownstreamPolicy, NotValidated, ReviewGraph, SelectedToken,
};

/// What a change reaches, what of it a review can rebuild, and what the policy plans.
pub(crate) struct ReviewScope {
    pub(crate) changed: BTreeSet<String>,
    pub(crate) affected: BTreeSet<String>,
    /// Affected SQL nodes reading an affected Python node, with that Python node.
    pub(crate) readers: BTreeMap<String, String>,
    pub(crate) rebuildable: BTreeSet<String>,
    pub(crate) critical: BTreeSet<String>,
    /// The changed rebuildable nodes and the downstream the policy keeps.
    pub(crate) planned: BTreeSet<String>,
}

/// The scope of `changed` over `graph` under `policy`.
pub(crate) fn review_scope(
    graph: &ReviewGraph,
    changed: &[ChangedNode],
    policy: DownstreamPolicy,
) -> ReviewScope {
    let changed: BTreeSet<String> = changed
        .iter()
        .filter(|node| graph.nodes.contains_key(&node.name))
        .map(|node| node.name.clone())
        .collect();
    let affected: BTreeSet<String> = descendants(graph, &changed);
    let readers: BTreeMap<String, String> = python_readers(graph, &affected);
    let rebuildable: BTreeSet<String> = affected
        .iter()
        .filter(|name| !readers.contains_key(*name))
        .filter(|name| graph.nodes.get(*name).is_some_and(|node| !node.python))
        .cloned()
        .collect();
    let critical: BTreeSet<String> = rebuildable
        .iter()
        .filter(|name| graph.nodes.get(*name).is_some_and(|node| node.critical))
        .cloned()
        .collect();
    let changed_rebuildable: BTreeSet<String> =
        changed.intersection(&rebuildable).cloned().collect();
    let downstream: BTreeSet<String> = rebuildable
        .difference(&changed_rebuildable)
        .cloned()
        .collect();
    let mut planned: BTreeSet<String> = changed_rebuildable.clone();
    planned.extend(policy_downstream(
        graph,
        policy,
        (&changed_rebuildable, &downstream),
        &critical,
    ));
    ReviewScope {
        changed,
        affected,
        readers,
        rebuildable,
        critical,
        planned,
    }
}

/// The planned nodes `select` keeps, or all of them without `--select`.
pub(crate) fn selected_scope(
    (graph, policy): (&ReviewGraph, DownstreamPolicy),
    scope: &ReviewScope,
    select: Option<&[SelectedToken]>,
) -> Result<BTreeSet<String>, ReviewPlanError> {
    let Some(tokens) = select else {
        return Ok(scope.planned.clone());
    };
    let mut selected: BTreeSet<String> = BTreeSet::new();
    for token in tokens {
        check_token(token, (graph, policy), (&scope.affected, &scope.planned))?;
        selected.extend(token.names.iter().cloned());
    }
    Ok(scope.planned.intersection(&selected).cloned().collect())
}

/// The validated nodes in dependency order, and the affected nodes left out with the reason.
pub(crate) fn split_affected(
    (graph, policy): (&ReviewGraph, DownstreamPolicy),
    scope: &ReviewScope,
    validated: &BTreeSet<String>,
) -> (Vec<String>, Vec<NotValidated>) {
    let mut kept: Vec<String> = Vec::new();
    let mut left_out: Vec<NotValidated> = Vec::new();
    for name in &graph.order {
        if validated.contains(name) {
            kept.push(name.clone());
        } else if scope.affected.contains(name) {
            left_out.push(NotValidated {
                name: name.clone(),
                reason: not_validated_reason(
                    graph,
                    name,
                    (&scope.changed, &scope.planned, &scope.readers),
                    policy,
                ),
            });
        }
    }
    (kept, left_out)
}

/// `names` in dependency order.
pub(crate) fn in_order(graph: &ReviewGraph, names: &BTreeSet<String>) -> Vec<String> {
    graph
        .order
        .iter()
        .filter(|name| names.contains(*name))
        .cloned()
        .collect()
}

fn selection_error(code: &str, message: String, help: &str) -> ReviewPlanError {
    ReviewPlanError {
        code: code.to_owned(),
        message,
        help: Some(help.to_owned()),
    }
}

/// Affected SQL nodes reading an affected Python node, directly or not, with that Python node.
pub(crate) fn python_readers(
    graph: &ReviewGraph,
    affected: &BTreeSet<String>,
) -> BTreeMap<String, String> {
    let upstream: BTreeMap<&str, Vec<&str>> = upstream_of(graph);
    let mut readers: BTreeMap<String, String> = BTreeMap::new();
    for name in graph.order.iter().filter(|name| affected.contains(*name)) {
        let Some(node) = graph.nodes.get(name) else {
            continue;
        };
        if node.python {
            continue;
        }
        let source: Option<String> = upstream
            .get(name.as_str())
            .into_iter()
            .flatten()
            .filter(|parent| affected.contains(**parent))
            .find_map(|parent| match graph.nodes.get(*parent) {
                Some(upstream_node) if upstream_node.python => Some((*parent).to_owned()),
                _ => readers.get(*parent).cloned(),
            });
        if let Some(source) = source {
            readers.insert(name.clone(), source);
        }
    }
    readers
}

/// The downstream nodes the policy validates, through rebuildable nodes only.
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

/// Rebuildable nodes between a change and a validated node, each with the node that needs it.
pub(crate) fn required_upstream(
    graph: &ReviewGraph,
    validated: &BTreeSet<String>,
    rebuildable: &BTreeSet<String>,
) -> Vec<AddedNode> {
    let mut added: Vec<AddedNode> = Vec::new();
    for name in graph.order.iter().filter(|name| validated.contains(*name)) {
        let single: BTreeSet<String> = BTreeSet::from([name.clone()]);
        for upstream in ancestors_within(graph, &single, rebuildable) {
            if !validated.contains(&upstream) && !added.iter().any(|node| node.name == upstream) {
                added.push(AddedNode {
                    name: upstream,
                    required_by: name.clone(),
                });
            }
        }
    }
    let position: BTreeMap<&str, usize> = graph
        .order
        .iter()
        .enumerate()
        .map(|(index, name)| (name.as_str(), index))
        .collect();
    added.sort_by_key(|node| position.get(node.name.as_str()).copied());
    added
}

/// Reject a token that matches nothing, only unchanged nodes, or only nodes outside the scope.
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
                "--select {} matches only downstream nodes that --downstream {} leaves out or \
                 that read Python nodes",
                token.token,
                policy_name(policy)
            ),
            "pass --downstream all to review every downstream SQL node",
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
    graph: &ReviewGraph,
    name: &str,
    (changed, scope, readers): (
        &BTreeSet<String>,
        &BTreeSet<String>,
        &BTreeMap<String, String>,
    ),
    policy: DownstreamPolicy,
) -> String {
    if let Some(node) = graph.nodes.get(name).filter(|node| node.python) {
        return format!("Python {}, not run by review", node.kind);
    }
    if let Some(python) = readers.get(name) {
        return format!("reads Python node {python}, not rebuilt by review");
    }
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
