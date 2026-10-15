//! Help that shows an exact authored snippet to add.

use crate::project::constants::SETTING_SNIPPET_INDENT;

/// `<purpose>, <target>:` followed by the exact lines to write, one per line.
#[must_use]
pub fn snippet_help_text(purpose: &str, target: &str, lines: &[String]) -> String {
    let snippet: Vec<String> = lines
        .iter()
        .map(|line| format!("{SETTING_SNIPPET_INDENT}{line}"))
        .collect();
    format!("{purpose}, {target}:\n{}", snippet.join("\n"))
}
