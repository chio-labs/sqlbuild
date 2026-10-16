//! The listed paths a shell-style pattern matches.

use std::path::Path;

use sqlbuild_core::text::main::glob_match::glob_match;

use crate::project_tree::_helpers::relative_paths::escaped_text;

/// Indexes of the `values` that `fnmatch.fnmatchcase(value, pattern)` accepts.
#[must_use]
pub fn project_tree_glob(values: &[&Path], pattern: &Path) -> Vec<usize> {
    let pattern: String = escaped_text(pattern);
    values
        .iter()
        .enumerate()
        .filter(|(_, value)| glob_match(&escaped_text(value), &pattern))
        .map(|(index, _)| index)
        .collect()
}
