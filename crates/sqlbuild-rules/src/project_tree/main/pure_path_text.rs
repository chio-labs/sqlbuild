//! `str(Path(path))` as `pathlib` spells it.

use std::ffi::OsString;
use std::path::Path;

use crate::project_tree::_helpers::relative_paths::{pure_parts, pure_text};

/// `str(Path(path))`: the anchor and components joined by the platform separator, or `.`.
#[must_use]
pub fn pure_path_text(path: &Path) -> OsString {
    pure_text(&pure_parts(path))
}
