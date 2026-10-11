//! `PurePosixPath(*parts).as_posix()` of parts `posix_parts` returned.

use crate::posix_path::constants::{CURRENT, DOUBLE_ROOT, ROOT};

/// The parts joined by `/` after their root, or `.` when there are none.
#[must_use]
pub fn posix_join(parts: &[&str]) -> String {
    match parts.split_first() {
        None => CURRENT.to_owned(),
        Some((root, rest)) if *root == ROOT || *root == DOUBLE_ROOT => {
            format!("{root}{}", rest.join(ROOT))
        }
        Some(_) => parts.join(ROOT),
    }
}
