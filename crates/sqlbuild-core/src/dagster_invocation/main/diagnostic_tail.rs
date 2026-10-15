//! Bounded process output for failure diagnostics.

use crate::dagster_invocation::constants::MAX_DIAGNOSTIC_CHARS;

/// The last characters of `value` kept in failure metadata.
#[must_use]
pub fn diagnostic_tail(value: &str) -> String {
    let count: usize = value.chars().count();
    value
        .chars()
        .skip(count.saturating_sub(MAX_DIAGNOSTIC_CHARS))
        .collect()
}
