//! One clipped batch step on a caller's timeline.

use crate::planner_strategy::types::Timeline;

/// `min(moment + step, end)`, keeping `moment + step` on ties as Python's `min` does.
pub(crate) fn clipped_step<T: Timeline>(
    timeline: &T,
    moment: &T::Moment,
    end: &T::Moment,
) -> Result<T::Moment, T::Error> {
    let next: T::Moment = timeline.advance(moment)?;
    Ok(if timeline.precedes(end, &next)? {
        end.clone()
    } else {
        next
    })
}
