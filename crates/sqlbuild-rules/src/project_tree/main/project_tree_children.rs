//! The listed paths directly inside one project directory.

use std::path::Path;

use crate::project_tree::_helpers::relative_paths::{pure_parent, pure_parts, same_path};
use crate::project_tree::models::PureParts;

/// Indexes of the `values` whose `Path(value).parent == Path(directory)`.
#[must_use]
pub fn project_tree_children(values: &[&Path], directory: &Path) -> Vec<usize> {
    let directory: PureParts = pure_parts(directory);
    values
        .iter()
        .enumerate()
        .filter(|(_, value)| same_path(&pure_parent(&pure_parts(value)), &directory))
        .map(|(index, _)| index)
        .collect()
}
