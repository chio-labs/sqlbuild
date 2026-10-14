//! An integer cursor range capped to its first or last batches.

use crate::planner_strategy::_helpers::python_int::python_int;
use crate::planner_strategy::models::{CapDirection, CappedBound};

/// The moved bound, or `None` when the batch size is not a positive integer.
pub fn cap_integer_bounds(
    (start, end): (i128, i128),
    batch_size: &str,
    max_batches: i128,
    direction: CapDirection,
) -> Option<CappedBound<i128>> {
    let size: i128 = python_int(batch_size).filter(|size| *size > 0)?;
    if direction == CapDirection::FromStart {
        return Some(CappedBound::End(end.min(start + size * max_batches)));
    }
    let batch_count: i128 = (end - start + size - 1).div_euclid(size).max(0);
    let skipped: i128 = (batch_count - max_batches).max(0);
    Some(CappedBound::Start(start + size * skipped))
}
