//! The versioned review JSON document.

use serde_json::{Value, json};

use crate::review_command::_helpers::json::{counts_json, finding_json, node_json, summary_json};
use crate::review_command::_helpers::outcome::outcome;
use crate::review_command::_helpers::wording::policy_name;
use crate::review_command::constants::REVIEW_REPORT_FORMAT_VERSION;
use crate::review_command::models::ReviewReport;

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
        "added": report.plan.added.iter().map(|node| json!({
            "name": node.name,
            "required_by": node.required_by,
        })).collect::<Vec<Value>>(),
        "hooks": report.plan.hooks,
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
