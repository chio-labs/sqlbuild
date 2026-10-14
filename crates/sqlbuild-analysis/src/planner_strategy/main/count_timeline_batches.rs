//! The number of batches between two aligned moments.

use crate::planner_strategy::_helpers::timeline::clipped_step;
use crate::planner_strategy::types::Timeline;

/// Steps from `start` until `end`, the last one clipped; equal bounds are one batch when asked.
pub fn count_timeline_batches<T: Timeline>(
    timeline: &T,
    (start, end): (T::Moment, T::Moment),
    equal_bounds_are_batch: bool,
) -> Result<i128, T::Error> {
    if equal_bounds_are_batch
        && !timeline.precedes(&start, &end)?
        && !timeline.precedes(&end, &start)?
    {
        return Ok(1);
    }
    let mut current: T::Moment = start;
    let mut count: i128 = 0;
    while timeline.precedes(&current, &end)? {
        current = clipped_step(timeline, &current, &end)?;
        count += 1;
    }
    Ok(count)
}
