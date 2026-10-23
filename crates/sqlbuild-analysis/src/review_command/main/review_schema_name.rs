//! The run-owned schema name of one review.

use crate::review_command::constants::{SCHEMA_COMMIT_DIGITS, SCHEMA_RUN_DIGITS};

/// `<prefix>_<YYYYMMDDTHHMMSSZ>_<commit>_<run>`, which `parse_review_schema_name` reads back.
#[must_use]
pub fn review_schema_name(prefix: &str, timestamp: &str, commit: &str, run_id: &str) -> String {
    let commit: String = commit
        .chars()
        .filter(char::is_ascii_hexdigit)
        .take(SCHEMA_COMMIT_DIGITS)
        .collect::<String>()
        .to_ascii_lowercase();
    let run: String = run_id
        .chars()
        .filter(char::is_ascii_hexdigit)
        .take(SCHEMA_RUN_DIGITS)
        .collect::<String>()
        .to_ascii_lowercase();
    format!("{prefix}_{timestamp}_{commit}_{run}")
}
