//! The run-owned schema name of one review.

use crate::review_command::constants::{SCHEMA_COMMIT_DIGITS, SCHEMA_RUN_DIGITS};

/// The first `digits` hex digits of `text`, lowercase and left-padded with zeros.
fn hex_part(text: &str, digits: usize) -> String {
    let hex: String = text
        .chars()
        .filter(char::is_ascii_hexdigit)
        .take(digits)
        .collect::<String>()
        .to_ascii_lowercase();
    format!("{hex:0>digits$}")
}

/// `<prefix>_<YYYYMMDDTHHMMSSZ>_<commit>_<run>` in lowercase, as `parse_review_schema_name` reads.
#[must_use]
pub fn review_schema_name(prefix: &str, timestamp: &str, commit: &str, run_id: &str) -> String {
    format!(
        "{prefix}_{timestamp}_{}_{}",
        hex_part(commit, SCHEMA_COMMIT_DIGITS),
        hex_part(run_id, SCHEMA_RUN_DIGITS)
    )
    .to_ascii_lowercase()
}
