//! Python's `fnmatch.fnmatchcase`.

use crate::text::_helpers::fnmatch::code_points_match;

/// Whether `name` matches the shell-style `pattern`, case-sensitively and across newlines.
#[must_use]
pub fn python_fnmatchcase(name: &str, pattern: &str) -> bool {
    let code_points: Vec<u32> = name.chars().map(u32::from).collect();
    code_points_match(&code_points, pattern)
}
