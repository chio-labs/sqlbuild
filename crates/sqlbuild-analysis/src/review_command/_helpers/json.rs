//! The parts of the versioned review JSON document.

use serde_json::{Value, json};

use crate::review_command::constants::{FINDING_NODE, NO_COMPARISON_MODE, NOT_VALIDATED_NODE};
use crate::review_command::models::{
    NodeComparison, NodeReport, ReviewFinding, ReviewReport, ValidationCounts,
};

pub(crate) fn comparison_json(comparison: &NodeComparison) -> Value {
    json!({
        "mode": comparison.mode,
        "complete": comparison.complete,
        "target_relation": comparison.target_relation,
        "branch_relation": comparison.branch_relation,
        "target_rows": comparison.target_rows,
        "branch_rows": comparison.branch_rows,
        "compared_rows": comparison.compared_rows,
        "unique_key": comparison.unique_key,
        "added_columns": comparison.added_columns,
        "removed_columns": comparison.removed_columns,
        "type_changes": comparison.type_changes.iter().map(|(column, target, branch)| {
            json!({"column": column, "target": target, "branch": branch})
        }).collect::<Vec<Value>>(),
        "branch_only_keys": comparison.branch_only_keys,
        "target_only_keys": comparison.target_only_keys,
        "columns": comparison.columns.iter().map(|column| json!({
            "column": column.column,
            "metric": column.metric,
            "target": column.target,
            "branch": column.branch,
            "limit": column.limit,
        })).collect::<Vec<Value>>(),
        "unchanged_columns": comparison.unchanged_columns,
    })
}

pub(crate) fn node_json(node: &NodeReport) -> Value {
    json!({
        "name": node.name,
        "kind": node.kind,
        "critical": node.critical,
        "changed": node.changed,
        "status": node.status,
        "reason": node.reason,
        "build_status": node.build_status,
        "comparison": node.comparison.as_ref().map(comparison_json),
        "affected_columns": node.affected_columns,
    })
}

pub(crate) fn finding_json(finding: &ReviewFinding) -> Value {
    json!({
        "node": finding.node,
        "kind": finding.kind,
        "metric": finding.metric,
        "column": finding.column,
        "target": finding.target_value,
        "branch": finding.branch_value,
        "limit": finding.limit,
        "examples": finding.examples.iter().map(|example| json!({
            "key": example.key,
            "target": example.target,
            "branch": example.branch,
        })).collect::<Vec<Value>>(),
    })
}

pub(crate) fn counts_json(counts: &ValidationCounts) -> Value {
    json!({
        "selected": counts.selected,
        "total": counts.total,
        "skipped": counts.total.saturating_sub(counts.selected),
        "passed": counts.passed,
        "failed": counts.failed,
        "failures": counts.failures,
    })
}

pub(crate) fn summary_json(report: &ReviewReport) -> Value {
    let built: usize = report
        .nodes
        .iter()
        .filter(|node| node.build_status.is_some())
        .count();
    let compared: usize = report
        .nodes
        .iter()
        .filter(|node| {
            node.comparison
                .as_ref()
                .is_some_and(|comparison| comparison.mode != NO_COMPARISON_MODE)
        })
        .count();
    json!({
        "changed": report.plan.changed.len() + report.changed_declarations.len(),
        "validated": report.plan.validated.len(),
        "built": built,
        "compared": compared,
        "tests": report.tests.selected,
        "findings": report.findings.len(),
        "nodes_with_findings": report.nodes.iter().filter(|node| node.status == FINDING_NODE).count(),
        "not_validated": report.nodes.iter().filter(|node| node.status == NOT_VALIDATED_NODE).count(),
        "incomplete": report.incomplete.len(),
    })
}
