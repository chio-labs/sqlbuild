//! One verbose warehouse inspection line.

use crate::progress::constants::SQL_PREVIEW_LENGTH;
use crate::progress::models::InspectionRecord;

fn collapse_whitespace(text: &str) -> String {
    text.split_whitespace().collect::<Vec<&str>>().join(" ")
}

fn row_count_text(row_count: Option<i64>) -> String {
    match row_count {
        None => "? rows".to_owned(),
        Some(1) => "1 row".to_owned(),
        Some(count) => format!("{count} rows"),
    }
}

/// `  inspect   0.12s  3 rows  SELECT ...`, with the SQL on one line and cut to the preview length.
#[must_use]
pub fn format_inspection_record(record: &InspectionRecord) -> String {
    let mut text: String = collapse_whitespace(&record.sql);
    if text.chars().count() > SQL_PREVIEW_LENGTH {
        let kept: String = text.chars().take(SQL_PREVIEW_LENGTH - 3).collect();
        text = format!("{kept}...");
    }
    let outcome: String = record.error.as_ref().map_or_else(
        || row_count_text(record.row_count),
        |error| format!("failed: {}", collapse_whitespace(error)),
    );
    format!(
        "  inspect {:6.2}s  {outcome}  {text}",
        record.elapsed_seconds
    )
}
