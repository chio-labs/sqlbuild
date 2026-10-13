//! The user-facing name of one SQL expectation row.

use crate::progress::constants::ASSERTION_PREFIX;

/// Assertions keep their name; compared models read as `expected <model>`.
#[must_use]
pub fn format_expectation_name(model_name: &str) -> String {
    if model_name.starts_with(ASSERTION_PREFIX) {
        return model_name.to_owned();
    }
    format!("expected {model_name}")
}
