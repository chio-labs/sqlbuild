//! `Path(path).as_posix()` as `pathlib` spells it.

use std::path::Path;

use crate::project_tree::_helpers::relative_paths::{posix_bytes, pure_parts};

/// `Path(path).as_posix()` as encoded bytes.
#[must_use]
pub fn pure_path_posix(path: &Path) -> Vec<u8> {
    posix_bytes(&pure_parts(path))
}
