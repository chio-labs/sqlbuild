//! The versioned review JSON document.

use serde_json::{Value, json};

use crate::review_command::_helpers::outcome::outcome;
use crate::review_command::_helpers::wording::policy_name;
use crate::review_command::constants::{
    FINDING_NODE, NOT_VALIDATED_NODE, REVIEW_REPORT_FORMAT_VERSION,
};
use crate::review_command::models::{
    NodeComparison, NodeReport, ReviewFinding, ReviewReport, ValidationCounts,
};

fn comparison_json(comparison: &NodeComparison) -> Value {
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

fn node_json(node: &NodeReport) -> Value {
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

fn finding_json(finding: &ReviewFinding) -> Value {
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

fn counts_json(counts: &ValidationCounts) -> Value {
    json!({
        "selected": counts.selected,
        "total": counts.total,
        "skipped": counts.total.saturating_sub(counts.selected),
        "passed": counts.passed,
        "failed": counts.failed,
        "failures": counts.failures,
    })
}

fn summary_json(report: &ReviewReport) -> Value {
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
                .is_some_and(|comparison| comparison.mode != "none")
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

/// The review as one pretty-printed JSON document, ending in a newline.
#[must_use]
pub fn render_review_json(report: &ReviewReport) -> String {
    let (status, exit_code) = outcome(report);
    let baseline = &report.baseline;
    let document: Value = json!({
        "format_version": REVIEW_REPORT_FORMAT_VERSION,
        "command": "review",
        "status": status,
        "exit_code": exit_code,
        "dry_run": report.dry_run,
        "version": report.version,
        "duration_seconds": (report.duration_seconds * 1000.0).round() / 1000.0,
        "since": {
            "ref": baseline.since_ref,
            "merge_base": baseline.merge_base,
            "head": baseline.head,
        },
        "against": baseline.against,
        "target": baseline.target,
        "downstream": policy_name(report.plan.policy),
        "summary": summary_json(report),
        "findings": report.findings.iter().map(finding_json).collect::<Vec<Value>>(),
        "changed": report.plan.changed.iter().map(|node| json!({
            "name": node.name,
            "kind": node.kind,
            "reasons": node.reasons,
        })).chain(report.changed_declarations.iter().map(|(kind, name, reason)| json!({
            "name": name,
            "kind": kind,
            "reasons": [reason],
        }))).collect::<Vec<Value>>(),
        "changes": report.changes_json,
        "critical": report.plan.critical,
        "validated": report.plan.validated,
        "not_validated": report.plan.not_validated.iter().map(|node| json!({
            "name": node.name,
            "reason": node.reason,
        })).collect::<Vec<Value>>(),
        "nodes": report.nodes.iter().map(node_json).collect::<Vec<Value>>(),
        "impact_edges": report.impact_edges.iter().map(|(upstream, downstream)| json!({
            "upstream": upstream,
            "downstream": downstream,
        })).collect::<Vec<Value>>(),
        "incomplete": report.incomplete.iter().map(|check| json!({
            "node": check.node,
            "check": check.check,
            "reason": check.reason,
        })).collect::<Vec<Value>>(),
        "baseline": {
            "target": baseline.against,
            "deferred": report.deferred,
            "incremental_starts": report.incremental_starts.iter().map(|start| json!({
                "node": start.node,
                "method": start.method,
                "reason": start.reason,
            })).collect::<Vec<Value>>(),
        },
        "tests": counts_json(&report.tests),
        "audits": counts_json(&report.audits),
        "review_schema": report.schema.as_ref().map(|schema| json!({
            "database": schema.database,
            "name": schema.name,
            "created": schema.created,
            "dropped": schema.dropped,
            "error": schema.error,
        })),
        "recall": report.invocation_id.as_ref().map(|id| json!({
            "invocation_id": id,
            "command": format!("sqb recall output {id}"),
        })),
        "error": report.error.as_ref().map(|error| json!({
            "code": error.code,
            "message": error.message,
            "help": error.help,
        })),
    });
    let mut text: String =
        serde_json::to_string_pretty(&document).unwrap_or_else(|_| String::from("{}"));
    text.push('\n');
    text
}
