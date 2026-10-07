//! Python's `sorted()` order of paths: part by part, each part by code point.

use crate::tree::_helpers::raw_names::{
    has_raw_segment, lowercase_code_points, path_code_points, segment_code_points,
};
use std::cmp::Ordering;

/// Python's path order on this platform; Windows paths compare their lowercased parts.
pub(crate) fn compare_relative_paths(left: &str, right: &str) -> Ordering {
    compare_paths(left, right, cfg!(windows))
}

/// `PurePosixPath` order, or `PureWindowsPath` order (`str.lower()` of each part) when asked.
pub(crate) fn compare_paths(left: &str, right: &str, case_insensitive: bool) -> Ordering {
    if !case_insensitive && !has_raw_segment(left) && !has_raw_segment(right) {
        return left.split('/').cmp(right.split('/'));
    }
    let key = |path: &str| -> Vec<Vec<u32>> {
        path.split('/')
            .map(|segment| {
                let points: Vec<u32> = segment_code_points(segment);
                if case_insensitive {
                    lowercase_code_points(&points)
                } else {
                    points
                }
            })
            .collect()
    };
    key(left).cmp(&key(right))
}

/// Python's order of `as_posix()` strings, with raw names surrogate-escaped.
pub(crate) fn compare_posix_text(left: &str, right: &str) -> Ordering {
    if !has_raw_segment(left) && !has_raw_segment(right) {
        return left.cmp(right);
    }
    path_code_points(left).cmp(&path_code_points(right))
}
