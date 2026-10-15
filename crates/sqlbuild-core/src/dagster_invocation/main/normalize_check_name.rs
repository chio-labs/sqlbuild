//! Dagster-safe check name segments.

use crate::dagster_invocation::constants::{CHECK_NAME_SEPARATOR, DEFAULT_CHECK_NAME};

/// `value` with every non-alphanumeric character replaced and outer separators trimmed.
#[must_use]
pub fn normalize_check_name(value: &str) -> String {
    let normalized: String = value
        .chars()
        .map(|character| {
            if character.is_alphanumeric() || character == CHECK_NAME_SEPARATOR {
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
