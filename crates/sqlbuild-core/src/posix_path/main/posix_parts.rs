//! `PurePosixPath(path).parts`.

use crate::posix_path::constants::{CURRENT, DOUBLE_ROOT, ROOT, SEPARATOR};

/// The root, if any, then every component except empty and `.` ones.
#[must_use]
pub fn posix_parts(path: &str) -> Vec<&str> {
    let mut parts: Vec<&str> = Vec::new();
    if path.starts_with(DOUBLE_ROOT) && !path[DOUBLE_ROOT.len()..].starts_with(SEPARATOR) {
        parts.push(DOUBLE_ROOT);
    } else if path.starts_with(SEPARATOR) {
        parts.push(ROOT);
    }
    parts.extend(
        path.split(SEPARATOR)
            .filter(|part| !part.is_empty() && *part != CURRENT),
    );
    parts
}
