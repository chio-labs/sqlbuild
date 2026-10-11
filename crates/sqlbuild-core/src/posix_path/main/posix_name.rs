//! `PurePosixPath(path).name`.

use crate::posix_path::constants::{DOUBLE_ROOT, ROOT};
use crate::posix_path::main::posix_parts::posix_parts;

/// The last component, or an empty name for a bare root or `.`.
#[must_use]
pub fn posix_name(path: &str) -> &str {
    match posix_parts(path).last() {
        Some(last) if *last != ROOT && *last != DOUBLE_ROOT => last,
        _ => "",
    }
}
