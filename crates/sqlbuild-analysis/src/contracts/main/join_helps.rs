//! Several help paragraphs joined into one help text.

use crate::contracts::_helpers::setting_help;

/// The paragraphs joined with one `= help:` label each.
#[must_use]
pub fn join_helps(helps: &[String]) -> String {
    setting_help::join_helps(helps)
}
