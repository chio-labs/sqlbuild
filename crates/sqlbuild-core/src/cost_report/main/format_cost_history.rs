//! The human `sqb cost history` table.

use crate::cli_text::models::CliStyle;
use crate::cost_report::_helpers::history::history_rows;
use crate::cost_report::models::CostRun;

/// `format_cost_history`: one aligned row per run, newest first as given.
#[must_use]
pub fn format_cost_history(runs: &[CostRun], matching_count: usize, use_color: bool) -> String {
    let style: CliStyle = CliStyle { use_color };
    let title: String = style.title("SQLBuild cost history");
    if runs.is_empty() {
        return [
            title,
            style.muted("No persisted cost runs."),
            style.muted(&format!("Showing 0 of {matching_count} matching runs.")),
        ]
        .join("\n");
    }
    let mut lines: Vec<String> = vec![title];
    lines.extend(history_rows(runs));
    lines.push(style.muted(&format!(
        "Showing {} of {matching_count} matching runs. Run `sqb cost <run_id>` for a full breakdown.",
        runs.len()
    )));
    lines.join("\n")
}
