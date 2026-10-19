//! The PASS/WARN/FAIL/SKIP/TOTAL footer of a dbt execution.

use crate::cli_text::main::format_summary_footer::format_summary_footer;
use crate::cli_text::models::{CliStyle, SummaryCount};
use crate::dbt_plan::constants::{FAIL_STATUSES, SKIP_STATUSES, SUCCESS_STATUSES, WARN_STATUSES};
use crate::dbt_plan::models::DbtExecutedNode;

/// The completion line and the counts with total elapsed time, or `None` without results.
#[must_use]
pub fn render_dbt_execution_summary(
    results: &[DbtExecutedNode],
    style: CliStyle,
) -> Option<String> {
    if results.is_empty() {
        return None;
    }
    let mut passed: i64 = 0;
    let mut warned: i64 = 0;
    let mut failed: i64 = 0;
    let mut skipped: i64 = 0;
    let mut elapsed: f64 = 0.0;
    for result in results {
        let status: String = result.status.to_lowercase();
        elapsed += result.execution_time.unwrap_or(0.0);
        if WARN_STATUSES.contains(&status.as_str()) {
            warned += 1;
        } else if FAIL_STATUSES.contains(&status.as_str()) {
            failed += 1;
        } else if SKIP_STATUSES.contains(&status.as_str()) {
            skipped += 1;
        } else if SUCCESS_STATUSES.contains(&status.as_str()) {
            passed += 1;
        }
    }
    let status_line: String = if failed > 0 {
        style.error("Completed with errors.")
    } else if warned > 0 {
        style.warning("Completed with warnings.")
    } else {
        style.success("Completed successfully.")
    };
    let counts: Vec<SummaryCount> = [
        ("PASS", passed),
        ("WARN", warned),
        ("FAIL", failed),
        ("SKIP", skipped),
        ("TOTAL", passed + warned + failed + skipped),
    ]
    .into_iter()
    .map(|(label, value)| SummaryCount {
        label: label.to_owned(),
        value,
    })
    .collect();
    let footer: String = format_summary_footer(style, &counts, Some(&format!("{elapsed:.2}s")));
    Some(format!("{status_line}\n{footer}"))
}
