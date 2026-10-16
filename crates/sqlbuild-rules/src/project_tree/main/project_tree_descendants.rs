//! The listed paths below one project directory.

use std::path::Path;

use crate::project_tree::_helpers::relative_paths::{posix_bytes, pure_parts};
use crate::project_tree::constants::POSIX_SEPARATOR_BYTE;

/// Indexes of the `values` below `directory` as `as_posix().rstrip("/") + "/"` prefixes them.
#[must_use]
pub fn project_tree_descendants(values: &[&Path], directory: Option<&Path>) -> Vec<usize> {
    let prefix: Vec<u8> = match directory {
        Some(directory) => {
            let mut text: Vec<u8> = posix_bytes(&pure_parts(directory));
            while text.last() == Some(&POSIX_SEPARATOR_BYTE) {
                text.pop();
            }
            text.push(POSIX_SEPARATOR_BYTE);
            text
        }
        None => Vec::new(),
    };
    values
        .iter()
        .enumerate()
        .filter(|(_, value)| value.as_os_str().as_encoded_bytes().starts_with(&prefix))
        .map(|(index, _)| index)
        .collect()
}
