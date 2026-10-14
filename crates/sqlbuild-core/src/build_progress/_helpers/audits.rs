//! Per-batch delta audit results folded into one display row per audit and phase.

use crate::build_progress::constants::{DELTA_AND_FINAL, ERROR, INSUFFICIENT, PASS, WARN};
use crate::build_progress::models::AuditResultText;

/// One aggregated audit row.
pub(crate) struct AuditDisplayEntry {
    pub(crate) label: &'static str,
    pub(crate) display_name: String,
    pub(crate) outcome: &'static str,
    pub(crate) total_row_count: i64,
    pub(crate) batch_pass: usize,
    pub(crate) batch_total: usize,
    pub(crate) reused: bool,
    pub(crate) executed_sql: Option<String>,
}

/// Audits sharing a name, column and run-scope phase.
type AuditGroup<'a> = (
    (&'a str, Option<&'a str>, &'a str),
    Vec<&'a AuditResultText>,
);

fn worst_outcome(results: &[&AuditResultText]) -> &'static str {
    for outcome in [ERROR, WARN, INSUFFICIENT] {
        if results.iter().any(|result| result.outcome == outcome) {
            return outcome;
        }
    }
    PASS
}

fn phase_label(has_delta: bool, phase: &str) -> &'static str {
    match (has_delta, phase == DELTA_AND_FINAL) {
        (false, _) => "audit",
        (true, true) => "audit (d)",
        (true, false) => "audit (f)",
    }
}

fn display_entry(
    (name, column, phase): (&str, Option<&str>, &str),
    results: &[&AuditResultText],
    has_delta: bool,
) -> AuditDisplayEntry {
    let mut total_row_count: i64 = 0;
    let mut batch_pass: usize = 0;
    let mut reused: bool = true;
    for result in results {
        total_row_count += result.row_count;
        batch_pass += usize::from(result.outcome == PASS);
        reused = reused && result.reused;
    }
    AuditDisplayEntry {
        label: phase_label(has_delta, phase),
        display_name: match column {
            Some(column) => format!("{name} ({column})"),
            None => name.to_owned(),
        },
        outcome: worst_outcome(results),
        total_row_count,
        batch_pass,
        batch_total: results.len(),
        reused,
        executed_sql: results
            .first()
            .and_then(|result| result.executed_sql.clone()),
    }
}

/// Group audits by name, column and run-scope phase in first-seen order.
pub(crate) fn aggregate_audit_results(audits: &[AuditResultText]) -> Vec<AuditDisplayEntry> {
    let has_delta: bool = audits
        .iter()
        .any(|audit| audit.run_scope_phase == DELTA_AND_FINAL);
    let mut groups: Vec<AuditGroup<'_>> = Vec::new();
    for audit in audits {
        let key = (
            audit.audit_name.as_str(),
            audit.attached_column_name.as_deref(),
            audit.run_scope_phase.as_str(),
        );
        match groups.iter_mut().find(|(existing, _)| *existing == key) {
            Some((_, members)) => members.push(audit),
            None => groups.push((key, vec![audit])),
        }
    }
    groups
        .into_iter()
        .map(|(key, results)| display_entry(key, &results, has_delta))
        .collect()
}
