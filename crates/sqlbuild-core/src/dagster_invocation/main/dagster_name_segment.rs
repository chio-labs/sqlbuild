//! The default Dagster translator's check-name segment.

use crate::dagster_invocation::_helpers::names::replace_runs;
use crate::dagster_invocation::constants::{DEFAULT_CHECK_NAME, NAME_SEPARATOR};

/// `re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_") or "check"`.
#[must_use]
pub fn dagster_name_segment(value: &str) -> String {
    let replaced: String = replace_runs(value, |character| {
        character.is_ascii_alphanumeric() || character == NAME_SEPARATOR
    });
    let trimmed: &str = replaced.trim_matches(NAME_SEPARATOR);
    if trimmed.is_empty() {
        DEFAULT_CHECK_NAME.to_owned()
    } else {
        trimmed.to_owned()
    }
}
