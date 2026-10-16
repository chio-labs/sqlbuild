//! The listed paths below one project directory.

use std::os::unix::ffi::OsStrExt;
use std::path::Path;

use crate::project_tree::_helpers::relative_paths::{joined_text, rooted_parts};
use crate::project_tree::constants::{DESCENDANT_SEPARATOR, SEPARATOR};

/// Indexes of the `values` below `directory` as `as_posix().rstrip("/") + "/"` prefixes them.
#[must_use]
pub fn project_tree_descendants(values: &[&Path], directory: Option<&Path>) -> Vec<usize> {
    let prefix: Vec<u8> = match directory {
        Some(directory) => {
            let mut text: Vec<u8> = joined_text(&rooted_parts(directory));
            while text.last() == Some(&SEPARATOR) {
                text.pop();
            }
            text.extend_from_slice(DESCENDANT_SEPARATOR);
            text
        }
        None => Vec::new(),
    };
    values
        .iter()
        .enumerate()
        .filter(|(_, value)| value.as_os_str().as_bytes().starts_with(&prefix))
        .map(|(index, _)| index)
        .collect()
}
