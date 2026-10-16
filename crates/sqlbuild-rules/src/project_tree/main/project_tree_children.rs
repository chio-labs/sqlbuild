//! The listed paths directly inside one project directory.

use std::path::Path;

use crate::project_tree::_helpers::relative_paths::{joined_text, parent_parts, rooted_parts};

/// Indexes of the `values` whose `PurePosixPath(value).parent == PurePosixPath(directory)`.
#[must_use]
pub fn project_tree_children(values: &[&Path], directory: &Path) -> Vec<usize> {
    let directory: Vec<u8> = joined_text(&rooted_parts(directory));
    values
        .iter()
        .enumerate()
        .filter(|(_, value)| joined_text(&parent_parts(&rooted_parts(value))) == directory)
        .map(|(index, _)| index)
        .collect()
}
