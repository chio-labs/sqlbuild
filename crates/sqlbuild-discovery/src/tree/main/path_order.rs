//! Python's sort order of project-relative paths.

use crate::tree::_helpers::ordering;
use std::cmp::Ordering;

/// Python's order of `as_posix()` strings, with names that are not UTF-8 surrogate-escaped.
pub fn compare_posix_text(left: &str, right: &str) -> Ordering {
    ordering::compare_posix_text(left, right)
}
