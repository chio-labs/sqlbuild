//! The result row of one finished scenario snapshot capture.

use crate::cli_text::models::CliStyle;
use crate::scenario_command::_helpers::rows::{
    capture_detail, capture_relation_rows, heading, indented_error_lines, snapshot_line,
};
use crate::scenario_command::constants::{FAIL_STATUS, PASS_STATUS, RETAINED_KIND_WIDTH};
use crate::scenario_command::models::CaptureRow;

/// The status row, its error, captured relations, snapshot path and retained inputs.
#[must_use]
pub fn render_capture_result(row: &CaptureRow, style: CliStyle) -> String {
    let status: String = style.status(if row.passed { PASS_STATUS } else { FAIL_STATUS });
    let detail: String = row
        .relations
        .as_deref()
        .map(capture_detail)
        .unwrap_or_default();
    let mut text: String = heading(&row.name, &status, &detail);
    if let Some(error) = row.error.as_ref().filter(|error| !error.message.is_empty()) {
        text.push_str(&indented_error_lines(error, style));
        if !row.retained {
            text.push_str("    Rerun with --retain to inspect scenario-owned artifacts.\n");
        }
    }
    if let (Some(relations), Some(path)) = (&row.relations, &row.snapshot_path) {
        text.push_str(&capture_relation_rows(relations, style));
        text.push_str(&snapshot_line(path));
    }
    if row.retained
        && let Some(inputs) = &row.retained_inputs
    {
        text.push_str("    Retained relations:\n");
        for fixture in &inputs.fixtures {
            text.push_str(&format!(
                "      {:<RETAINED_KIND_WIDTH$} {} -> {}\n",
                fixture.kind, fixture.logical_name, fixture.physical_name
            ));
        }
        for seed in &inputs.seeds {
            text.push_str(&format!("      seed   {seed}\n"));
        }
    }
    text
}
