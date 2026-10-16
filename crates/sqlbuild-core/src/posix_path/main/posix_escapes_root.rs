//! Whether a `PurePosixPath` leaves the directory it is relative to.

use crate::posix_path::constants::{DOUBLE_ROOT, PARENT, ROOT};
use crate::posix_path::main::posix_parts::posix_parts;

/// `PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts`.
#[must_use]
pub fn posix_escapes_root(path: &str) -> bool {
    posix_parts(path)
        .iter()
        .any(|part| *part == ROOT || *part == DOUBLE_ROOT || *part == PARENT)
}
