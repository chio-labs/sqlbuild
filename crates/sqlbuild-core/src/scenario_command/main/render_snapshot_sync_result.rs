//! The result row of one scenario captured by `--sync-snapshots` or `--refresh`.

use crate::cli_text::models::CliStyle;
use crate::scenario_command::_helpers::rows::{
    capture_detail, capture_relation_rows, heading, indented_error_lines, snapshot_line,
};
use crate::scenario_command::constants::FAIL_STATUS;
use crate::scenario_command::models::CaptureRow;

/// `CAPTURED`, `REFRESHED` or `FAIL`, its error, captured relations and snapshot path.
#[must_use]
pub fn render_snapshot_sync_result(row: &CaptureRow, refresh: bool, style: CliStyle) -> String {
    let success: &str = if refresh { "REFRESHED" } else { "CAPTURED" };
    let status: String = style.status(if row.passed { success } else { FAIL_STATUS });
    let detail: String = row
        .relations
        .as_deref()
        .map(capture_detail)
        .unwrap_or_default();
    let mut text: String = heading(&row.name, &status, &detail);
    if let Some(error) = row.error.as_ref().filter(|error| !error.message.is_empty()) {
        text.push_str(&indented_error_lines(error, style));
    }
    if let Some(relations) = &row.relations {
        text.push_str(&capture_relation_rows(relations, style));
        if let Some(path) = &row.snapshot_path {
            text.push_str(&snapshot_line(path));
        }
    }
    text
}
