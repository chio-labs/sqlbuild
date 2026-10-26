//! The leading summary of a failed invocation: what failed, before how the command exited.

use crate::dagster_invocation::constants::MAX_SUMMARIZED_FAILURES;
use crate::dagster_invocation::models::{AssetFailure, FailedCheck};

fn check_line(check: &FailedCheck) -> String {
    let mut line: String = format!("{} {}", check.kind, check.name);
    match (&check.asset_name, &check.column_name) {
        (Some(asset), Some(column)) => line.push_str(&format!(" on {asset}.{column}")),
        (Some(asset), None) => line.push_str(&format!(" on {asset}")),
        (None, _) => {}
    }
    match check.row_count {
        Some(1) => line.push_str(": 1 failing row"),
        Some(count) => line.push_str(&format!(": {count} failing rows")),
        None => line.push_str(&format!(": {}", check.status)),
    }
    line
}

fn asset_line(failure: &AssetFailure) -> String {
    let mut line: String = format!("{} {}: {}", failure.kind, failure.name, failure.status);
    if let Some(phase) = &failure.failed_phase {
        line.push_str(&format!(" during {phase}"));
    }
    line
}

/// `Failed: …` followed by one line per failed check, then per failed asset, at most [`MAX_SUMMARIZED_FAILURES`] of them and `and N more`; empty when nothing is known to have failed.
#[must_use]
pub fn failure_summary(checks: &[FailedCheck], assets: &[AssetFailure]) -> String {
    let lines: Vec<String> = checks
        .iter()
        .map(check_line)
        .chain(assets.iter().map(asset_line))
        .collect();
    if lines.is_empty() {
        return String::new();
    }
    let mut counts: Vec<String> = Vec::new();
    for (count, singular, plural) in [
        (checks.len(), "check", "checks"),
        (assets.len(), "asset", "assets"),
    ] {
        match count {
            0 => {}
            1 => counts.push(format!("1 {singular}")),
            _ => counts.push(format!("{count} {plural}")),
        }
    }
    let mut summary: Vec<String> = vec![format!("Failed: {}", counts.join(", "))];
    summary.extend(
        lines
            .iter()
            .take(MAX_SUMMARIZED_FAILURES)
            .map(|line| format!("  {line}")),
    );
    if lines.len() > MAX_SUMMARIZED_FAILURES {
        summary.push(format!(
            "  and {} more",
            lines.len() - MAX_SUMMARIZED_FAILURES
        ));
    }
    summary.join("\n")
}
