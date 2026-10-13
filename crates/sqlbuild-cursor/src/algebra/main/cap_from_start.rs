//! `cap_from_start`: the leading intervals a batch cap keeps.

use std::ops::Range;

/// `items[:max(count, 0)]` as a range over `length` items.
#[must_use]
pub fn cap_from_start(length: usize, count: i64) -> Range<usize> {
    0..usize::try_from(count).unwrap_or(0).min(length)
}
