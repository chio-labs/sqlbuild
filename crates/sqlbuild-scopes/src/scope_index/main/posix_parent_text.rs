//! The parent of a `/`-separated path as Python's `Path.as_posix` prints it.

use crate::scope_index::constants::{CURRENT_PATH_COMPONENT, PATH_SEPARATOR};
use crate::scope_index::main::posix_path_text::posix_path_text;

/// `Path(path).parent.as_posix()` of a normalized relative path.
#[must_use]
pub fn posix_parent_text(path: &str) -> String {
    match path.rfind(PATH_SEPARATOR) {
        Some(index) => posix_path_text(&path[..index]),
        None => CURRENT_PATH_COMPONENT.to_owned(),
    }
}
