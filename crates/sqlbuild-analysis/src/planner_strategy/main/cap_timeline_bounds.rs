//! A timestamp cursor range capped to its first or last batches.

use crate::planner_strategy::_helpers::timeline::clipped_step;
use crate::planner_strategy::models::{CapDirection, CappedBound};
use crate::planner_strategy::types::Timeline;

/// The new end after `max_batches` steps from the start, or the start of the last `max_batches` batches.
pub fn cap_timeline_bounds<T: Timeline>(
    timeline: &T,
    (start, end): (T::Moment, T::Moment),
    max_batches: i128,
    direction: CapDirection,
) -> Result<CappedBound<T::Moment>, T::Error> {
    if direction == CapDirection::FromStart {
        let mut capped_end: T::Moment = start;
        for _ in 0..max_batches.max(0) {
            capped_end = clipped_step(timeline, &capped_end, &end)?;
        }
        return Ok(CappedBound::End(capped_end));
    }
    let mut boundaries: Vec<T::Moment> = vec![start];
    while let Some(last) = boundaries.last().cloned() {
        if !timeline.precedes(&last, &end)? {
            break;
        }
        boundaries.push(clipped_step(timeline, &last, &end)?);
    }
    let last_index: usize = boundaries.len().saturating_sub(1);
    let kept: usize = usize::try_from(max_batches).unwrap_or(0).min(last_index);
    Ok(CappedBound::Start(
        boundaries.swap_remove(last_index - kept),
    ))
}
