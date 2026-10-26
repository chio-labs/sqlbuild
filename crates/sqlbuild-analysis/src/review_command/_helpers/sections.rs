//! The report sections the Markdown and terminal renderers share.

use crate::review_command::constants::{CLONE_START, NO_COMPARISON_MODE};
use sqlbuild_core::command_output::main::short_invocation_id::short_invocation_id;
use std::collections::{BTreeMap, BTreeSet};

use crate::review_command::_helpers::outcome::outcome;
use crate::review_command::_helpers::wording::{counted, duration_text, joined, policy_name};
use crate::review_command::constants::{
    FAILED_STATUS, FINDING_NODE, FINDINGS_STATUS, INCOMPLETE_STATUS, NOT_VALIDATED_NODE,
    PASSED_STATUS, PLANNED_STATUS,
};
use crate::review_command::models::{NodeReport, ReviewFinding, ReviewReport};

/// Whether names render as Markdown code spans.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Style {
    pub(crate) markdown: bool,
}

impl Style {
    pub(crate) fn code(self, text: &str) -> String {
        if self.markdown {
            format!("`{}`", text.replace('`', "'"))
        } else {
            text.to_owned()
        }
    }
}

/// `Review passed`, `Review needs a fix: 2 findings`, `Review incomplete`, `Review failed`.
pub(crate) fn headline(report: &ReviewReport) -> String {
    let (status, _) = outcome(report);
    match status {
        PASSED_STATUS => "Review passed".to_owned(),
        FINDINGS_STATUS => format!(
            "Review needs a fix: {}",
            counted(report.findings.len(), "finding", "findings")
        ),
        INCOMPLETE_STATUS => format!(
            "Review incomplete: {}",
            counted(report.incomplete.len(), "check", "checks")
        ),
        PLANNED_STATUS => "Review plan (dry run)".to_owned(),
        FAILED_STATUS => "Review failed".to_owned(),
        other => format!("Review {other}"),
    }
}

/// The one line under the title: refs, target, exit code, duration and version.
pub(crate) fn context_line(report: &ReviewReport, style: Style) -> String {
    let (_, exit_code) = outcome(report);
    let baseline = &report.baseline;
    let short = |sha: &str| sha.chars().take(7).collect::<String>();
    let mut parts: Vec<String> = vec![format!(
        "since {} ({})",
        style.code(&baseline.since_ref),
        short(&baseline.merge_base)
    )];
    if !baseline.head.is_empty() {
        parts.push(format!("head {}", short(&baseline.head)));
    }
    parts.push(format!("against {}", style.code(&baseline.against)));
    parts.push(format!("exit {exit_code}"));
    parts.push(duration_text(report.duration_seconds));
    parts.push(format!("sqlbuild {}", report.version));
    parts.join(" · ")
}

pub(crate) fn built_count(report: &ReviewReport) -> usize {
    report
        .nodes
        .iter()
        .filter(|node| node.build_status.is_some())
        .count()
}

pub(crate) fn compared_count(report: &ReviewReport) -> usize {
    report
        .nodes
        .iter()
        .filter(|node| {
            node.comparison
                .as_ref()
                .is_some_and(|comparison| comparison.mode != NO_COMPARISON_MODE)
        })
        .count()
}

pub(crate) fn not_validated_count(report: &ReviewReport) -> usize {
    report
        .nodes
        .iter()
        .filter(|node| node.status == NOT_VALIDATED_NODE)
        .count()
}

/// `(label, count)` of the summary table, in column order.
pub(crate) fn summary_counts(report: &ReviewReport) -> Vec<(&'static str, usize)> {
    vec![
        (
            "Changed",
            report.plan.changed.len() + report.changed_declarations.len(),
        ),
        ("Built", built_count(report)),
        ("Compared", compared_count(report)),
        ("Tests", report.tests.selected),
        ("Findings", report.findings.len()),
        ("Not validated", not_validated_count(report)),
        ("Incomplete", report.incomplete.len()),
    ]
}

/// `order_totals.amount: values differ in 2 of 5 rows (prod → branch), limit exact match`.
pub(crate) fn finding_text(finding: &ReviewFinding, against: &str, style: Style) -> String {
    let subject: String = match &finding.column {
        Some(column) => style.code(&format!("{}.{column}", finding.node)),
        None => style.code(&finding.node),
    };
    let values: String = match (&finding.target_value, &finding.branch_value) {
        (Some(target), Some(branch)) => format!(": {against} {target} → branch {branch}"),
        (Some(target), None) => format!(": {against} {target}"),
        (None, Some(branch)) => format!(": branch {branch}"),
        (None, None) => String::new(),
    };
    format!(
        "{subject} {}{values} (limit: {})",
        finding.metric, finding.limit
    )
}

/// `order_id=3: 12.5 → 13.0` lines of one finding.
pub(crate) fn example_lines(finding: &ReviewFinding, style: Style) -> Vec<String> {
    finding
        .examples
        .iter()
        .map(|example| match (&example.target, &example.branch) {
            (Some(target), Some(branch)) => format!(
                "{}: {} → {}",
                example.key,
                style.code(target),
                style.code(branch)
            ),
            (None, Some(branch)) => format!("{}: branch only {}", example.key, style.code(branch)),
            (Some(target), None) => format!("{}: target only {}", example.key, style.code(target)),
            (None, None) => example.key.clone(),
        })
        .collect()
}

fn node_status(node: &NodeReport) -> String {
    let mut status: String = match node.status.as_str() {
        NOT_VALIDATED_NODE => format!(
            "not validated: {}",
            node.reason.as_deref().unwrap_or("left out")
        ),
        other => match &node.reason {
            Some(reason) => format!("{other}: {reason}"),
            None => other.to_owned(),
        },
    };
    if node.critical {
        status.push_str(", critical");
    }
    status
}

fn node_line(node: &NodeReport, style: Style) -> String {
    let mut line: String = format!("{} [{}]", style.code(&node.name), node_status(node));
    if !node.affected_columns.is_empty() {
        let columns: Vec<String> = node
            .affected_columns
            .iter()
            .map(|column| style.code(column))
            .collect();
        line.push_str(&format!(" columns: {}", columns.join(", ")));
    }
    line
}

/// One node waiting to be drawn in the impact tree, with the prefix its line starts with.
struct TreeEntry<'a> {
    name: &'a str,
    prefix: String,
    last: bool,
    is_root: bool,
}

/// The impact tree, one line per node, from the changed roots downstream.
pub(crate) fn impact_tree(report: &ReviewReport, style: Style) -> Vec<String> {
    let nodes: BTreeMap<&str, &NodeReport> = report
        .nodes
        .iter()
        .map(|node| (node.name.as_str(), node))
        .collect();
    let mut children: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    let mut has_parent: BTreeSet<&str> = BTreeSet::new();
    for (upstream, downstream) in &report.impact_edges {
        children
            .entry(upstream.as_str())
            .or_default()
            .push(downstream.as_str());
        has_parent.insert(downstream.as_str());
    }
    let order: BTreeMap<&str, usize> = report
        .nodes
        .iter()
        .enumerate()
        .map(|(index, node)| (node.name.as_str(), index))
        .collect();
    for list in children.values_mut() {
        list.sort_by_key(|name| order.get(name).copied().unwrap_or(usize::MAX));
    }
    let mut lines: Vec<String> = Vec::new();
    let mut shown: BTreeSet<&str> = BTreeSet::new();
    let roots: Vec<&NodeReport> = report
        .nodes
        .iter()
        .filter(|node| node.changed || !has_parent.contains(node.name.as_str()))
        .collect();
    for root in roots {
        if shown.contains(root.name.as_str()) {
            continue;
        }
        let mut stack: Vec<TreeEntry<'_>> = vec![TreeEntry {
            name: &root.name,
            prefix: String::new(),
            last: true,
            is_root: true,
        }];
        while let Some(TreeEntry {
            name,
            prefix,
            last,
            is_root,
        }) = stack.pop()
        {
            let Some(node) = nodes.get(name) else {
                continue;
            };
            let branch: &str = if is_root {
                ""
            } else if last {
                "└── "
            } else {
                "├── "
            };
            if !shown.insert(name) {
                lines.push(format!(
                    "{prefix}{branch}{} (shown above)",
                    style.code(name)
                ));
                continue;
            }
            lines.push(format!("{prefix}{branch}{}", node_line(node, style)));
            let child_prefix: String = if is_root {
                String::new()
            } else if last {
                format!("{prefix}    ")
            } else {
                format!("{prefix}│   ")
            };
            let next: &[&str] = children.get(name).map_or(&[], Vec::as_slice);
            for (index, child) in next.iter().enumerate().rev() {
                stack.push(TreeEntry {
                    name: child,
                    prefix: child_prefix.clone(),
                    last: index + 1 == next.len(),
                    is_root: false,
                });
            }
        }
    }
    lines
}

/// `stg_orders (model): model SQL changed` lines.
pub(crate) fn changed_lines(report: &ReviewReport, style: Style) -> Vec<String> {
    let mut lines: Vec<String> = report
        .plan
        .changed
        .iter()
        .map(|node| {
            format!(
                "{} ({}): {}",
                style.code(&node.name),
                node.kind,
                joined(&node.reasons)
            )
        })
        .collect();
    for (kind, name, reason) in &report.changed_declarations {
        lines.push(format!("{kind} {}: {reason}", style.code(name)));
    }
    lines
}

pub(crate) fn incomplete_lines(report: &ReviewReport, style: Style) -> Vec<String> {
    report
        .incomplete
        .iter()
        .map(|check| {
            format!(
                "{} {}: {}",
                style.code(&check.node),
                check.check,
                check.reason
            )
        })
        .collect()
}

pub(crate) fn baseline_lines(report: &ReviewReport, style: Style) -> Vec<String> {
    let against: String = style.code(&report.baseline.against);
    let mut lines: Vec<String> = Vec::new();
    if report.deferred.is_empty() {
        lines.push(format!("Compared with {against}; no upstream read from it"));
    } else {
        let deferred: Vec<String> = report
            .deferred
            .iter()
            .map(|name| style.code(name))
            .collect();
        lines.push(format!(
            "Unchanged upstream read from {against}: {}",
            deferred.join(", ")
        ));
    }
    for start in &report.incremental_starts {
        let method: &str = if start.method == CLONE_START {
            "cloned from the target"
        } else {
            "full refresh"
        };
        lines.push(format!(
            "Incremental {}: {method} ({})",
            style.code(&start.node),
            start.reason
        ));
    }
    let new_nodes: Vec<String> = report
        .nodes
        .iter()
        .filter(|node| {
            node.comparison.as_ref().is_some_and(|comparison| {
                comparison.mode == NO_COMPARISON_MODE && comparison.target_relation.is_none()
            })
        })
        .map(|node| style.code(&node.name))
        .collect();
    if !new_nodes.is_empty() {
        lines.push(format!(
            "Not in {against}, so built but not compared: {}",
            new_nodes.join(", ")
        ));
    }
    lines
}

pub(crate) fn tests_lines(report: &ReviewReport) -> Vec<String> {
    let tests = &report.tests;
    let audits = &report.audits;
    let mut lines: Vec<String> = vec![
        format!(
            "Unit tests: {} of {} ran ({} unaffected skipped): {} passed, {} failed",
            tests.selected,
            tests.total,
            tests.total.saturating_sub(tests.selected),
            tests.passed,
            tests.failed
        ),
        format!(
            "Audits: {} ran: {} passed, {} failed",
            audits.selected, audits.passed, audits.failed
        ),
    ];
    for failure in tests.failures.iter().chain(&audits.failures) {
        lines.push(format!("failed: {failure}"));
    }
    lines
}

pub(crate) fn run_lines(report: &ReviewReport, style: Style) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    if let Some(schema) = &report.schema {
        let qualified: String = match &schema.database {
            Some(database) => format!("{database}.{}", schema.name),
            None => schema.name.clone(),
        };
        let state: String = match (&schema.error, schema.created, schema.dropped) {
            (Some(error), _, _) => format!("not dropped: {error}"),
            (None, false, _) => "not created".to_owned(),
            (None, true, true) => "dropped".to_owned(),
            (None, true, false) => "not dropped".to_owned(),
        };
        lines.push(format!("Review schema {}: {state}", style.code(&qualified)));
    }
    let mut policy: String = format!("Downstream policy: {}", policy_name(report.plan.policy));
    if !report.plan.critical.is_empty() {
        let critical: Vec<String> = report
            .plan
            .critical
            .iter()
            .map(|name| style.code(name))
            .collect();
        policy.push_str(&format!(" (critical: {})", critical.join(", ")));
    }
    lines.push(policy);
    for added in &report.plan.added {
        lines.push(format!(
            "Also built: {}, because {} depends on it",
            style.code(&added.name),
            style.code(&added.required_by)
        ));
    }
    if !report.plan.hooks.is_empty() {
        let hooked: Vec<String> = report
            .plan
            .hooks
            .iter()
            .map(|name| style.code(name))
            .collect();
        lines.push(format!(
            "Hooks run against the review schema: {}",
            hooked.join(", ")
        ));
    }
    if let Some(id) = &report.invocation_id {
        lines.push(format!(
            "Recall: {}",
            style.code(&format!("sqb recall output {}", short_invocation_id(id)))
        ));
    }
    if let Some(error) = &report.error {
        let mut line: String = format!("Error [{}]: {}", error.code, error.message);
        if let Some(help) = &error.help {
            line.push_str(&format!(" ({help})"));
        }
        lines.push(line);
    }
    lines
}

/// Whether a node has comparison evidence worth a per-model section.
pub(crate) fn has_evidence(node: &NodeReport) -> bool {
    node.status == FINDING_NODE
        || node.comparison.as_ref().is_some_and(|comparison| {
            !comparison.columns.is_empty()
                || !comparison.added_columns.is_empty()
                || !comparison.removed_columns.is_empty()
                || !comparison.type_changes.is_empty()
        })
}
