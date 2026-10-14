//! The number of batches in an integer cursor range.

use crate::planner_strategy::_helpers::python_int::python_int;

/// Batches of `batch_size` from `start` up to `end`; equal bounds are one batch when asked.
pub fn count_integer_batches(
    (start, end): (i128, i128),
    batch_size: &str,
    equal_bounds_are_batch: bool,
) -> i128 {
    let Some(size) = python_int(batch_size) else {
        return 0;
    };
    if equal_bounds_are_batch && start == end {
        return 1;
    }
    if size <= 0 || start >= end {
        return 0;
    }
    (end - start + size - 1).div_euclid(size)
}
