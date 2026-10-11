//! The help that shows the YAML entry describing a declared seed or source.

use crate::contracts::main::snippet_help::snippet_help;

/// `to describe <kind> '<name>', add `description` to its entry in <path>:` and its lines.
#[must_use]
pub fn yaml_help(kind: &str, name: &str, path: &str) -> String {
    snippet_help(
        &format!("to describe {kind} '{name}'"),
        &format!("add `description` to its entry in {path}"),
        &[
            format!("- name: {name}"),
            format!("  description: What one row of {name} represents"),
        ],
    )
}
