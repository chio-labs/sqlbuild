//! The completion text of the transient `Formatting SQL` status line.

use crate::format_command::models::LintReport;

/// Whether the run failed, and its status message after `elapsed` seconds.
#[must_use]
pub fn render_format_status(report: &LintReport, elapsed: f64) -> (bool, String) {
    let faults: usize = report.fault_count();
    if faults > 0 {
        return (
            true,
            format!("Formatting SQL  ERROR  ({elapsed:.2}s; {faults} faults)"),
        );
    }
    (
        false,
        format!(
            "Formatting SQL  OK  ({elapsed:.2}s; {} files checked, {} changed)",
            report.files_checked,
            report.formatted_files.len()
        ),
    )
}
