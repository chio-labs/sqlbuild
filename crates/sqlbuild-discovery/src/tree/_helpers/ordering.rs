//! Python's `sorted()` order of paths: part by part, each part by code point.

use std::cmp::Ordering;

pub(crate) fn compare_relative_paths(left: &str, right: &str) -> Ordering {
    left.split('/').cmp(right.split('/'))
}
