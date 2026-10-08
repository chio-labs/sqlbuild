//! Path-default glob matching and specificity, as `path_defaults/_helpers/matching.py`.

use crate::path_defaults::constants::{RECURSIVE_SEGMENT_GLOB, SINGLE_SEGMENT_GLOB};

/// Return whether a path-default pattern matches a prefix of the model path's segments.
pub(crate) fn matches_prefix(path_parts: &[&str], key: &str) -> bool {
    let pattern: Vec<&str> = key.split('/').collect();
    let mut table = vec![vec![false; path_parts.len() + 1]; pattern.len() + 1];
    table[pattern.len()].fill(true);
    for pattern_index in (0..pattern.len()).rev() {
        let part = pattern[pattern_index];
        for path_index in (0..=path_parts.len()).rev() {
            table[pattern_index][path_index] = if part == RECURSIVE_SEGMENT_GLOB {
                table[pattern_index + 1][path_index]
                    || (path_index < path_parts.len() && table[pattern_index][path_index + 1])
            } else {
                path_index < path_parts.len()
                    && (part == SINGLE_SEGMENT_GLOB || part == path_parts[path_index])
                    && table[pattern_index + 1][path_index + 1]
            };
        }
    }
    table[0][0]
}

fn is_glob(part: &str) -> bool {
    part == SINGLE_SEGMENT_GLOB || part == RECURSIVE_SEGMENT_GLOB
}

/// Return whether a key holds a `*` or `**` segment.
pub(crate) fn is_wildcard(key: &str) -> bool {
    key.split('/').any(is_glob)
}

/// Return the number of `/`-separated segments in a key.
pub(crate) fn segment_count(key: &str) -> usize {
    key.split('/').count()
}

/// Return the literal, single-glob and negated recursive-glob segment counts.
pub(crate) fn specificity(key: &str) -> (usize, usize, isize) {
    let parts: Vec<&str> = key.split('/').collect();
    let literal = parts.iter().filter(|part| !is_glob(part)).count();
    let single = parts
        .iter()
        .filter(|part| **part == SINGLE_SEGMENT_GLOB)
        .count();
    let recursive = parts
        .iter()
        .filter(|part| **part == RECURSIVE_SEGMENT_GLOB)
        .count();
    (
        literal,
        single,
        -isize::try_from(recursive).unwrap_or(isize::MAX),
    )
}
