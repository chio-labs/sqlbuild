//! `cap_from_end`: the trailing intervals a batch cap keeps.

use std::ops::Range;

/// `items[-count:] if count > 0 else ()` as a range over `length` items.
#[must_use]
pub fn cap_from_end(length: usize, count: i64) -> Range<usize> {
    let kept: usize = usize::try_from(count).unwrap_or(0).min(length);
    length - kept..length
}
