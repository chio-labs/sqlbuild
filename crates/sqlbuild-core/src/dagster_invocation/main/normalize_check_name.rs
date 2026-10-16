//! Dagster-safe check name segments.

use crate::dagster_invocation::constants::{CHECK_NAME_SEPARATOR, DEFAULT_CHECK_NAME};
use crate::text::main::python_isalnum::python_isalnum;

/// `value` with every character Python's `str.isalnum` rejects replaced and outer separators trimmed.
#[must_use]
pub fn normalize_check_name(value: &str) -> String {
    let normalized: String = value
        .chars()
        .map(|character| {
            if python_isalnum(character) || character == CHECK_NAME_SEPARATOR {
                character
            } else {
                CHECK_NAME_SEPARATOR
            }
        })
        .collect();
    let trimmed: &str = normalized.trim_matches(CHECK_NAME_SEPARATOR);
    if trimmed.is_empty() {
        DEFAULT_CHECK_NAME.to_owned()
    } else {
        trimmed.to_owned()
    }
}
