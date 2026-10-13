//! The heading of one check group.

/// `Python checks: <group>` and a blank line.
#[must_use]
pub fn check_group_header(group: &str) -> String {
    format!("Python checks: {group}\n\n")
}
