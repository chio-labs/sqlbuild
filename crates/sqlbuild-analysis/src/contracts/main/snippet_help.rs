//! A diagnostic help that shows the exact lines to write.

use crate::contracts::_helpers::setting_help;

/// `<purpose>, <target>:` followed by the exact lines to write, one per line.
#[must_use]
pub fn snippet_help(purpose: &str, target: &str, lines: &[String]) -> String {
    setting_help::snippet_help(purpose, target, lines)
}
