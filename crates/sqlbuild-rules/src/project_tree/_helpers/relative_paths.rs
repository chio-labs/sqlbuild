//! `PurePosixPath` reads of a project-relative path over its raw bytes.

use std::os::unix::ffi::OsStrExt;
use std::path::Path;

use crate::project_tree::constants::{CURRENT, PARENT, SEPARATOR};

/// The components `PurePosixPath(path).parts` keeps after any root.
pub(crate) fn parts(path: &Path) -> Vec<&[u8]> {
    path.as_os_str()
        .as_bytes()
        .split(|byte| *byte == SEPARATOR)
        .filter(|part| !part.is_empty() && *part != CURRENT)
        .collect()
}

/// `PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts`.
pub(crate) fn escapes(path: &Path) -> bool {
    path.as_os_str().as_bytes().first() == Some(&SEPARATOR) || parts(path).contains(&PARENT)
}
