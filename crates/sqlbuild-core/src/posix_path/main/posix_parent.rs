//! `PurePosixPath(path).parent.as_posix()`.

use crate::posix_path::constants::{DOUBLE_ROOT, ROOT};
use crate::posix_path::main::posix_join::posix_join;
use crate::posix_path::main::posix_parts::posix_parts;

/// The path without its last component; a bare root or `.` is its own parent.
#[must_use]
pub fn posix_parent(path: &str) -> String {
    let parts: Vec<&str> = posix_parts(path);
    match parts.as_slice() {
        [root] if *root == ROOT || *root == DOUBLE_ROOT => (*root).to_owned(),
        [] => posix_join(&[]),
        [init @ .., _] => posix_join(init),
    }
}
