//! `clamp`: the intersection of two half-open cursor intervals.

use crate::algebra::_helpers::intervals::clamp_interval;
use crate::algebra::errors::CursorError;
use crate::algebra::models::Interval;
use crate::algebra::types::ZoneRules;

/// `interval` limited to `bounds`, or `None` when they do not overlap.
pub fn clamp(
    interval: &Interval,
    bounds: &Interval,
    rules: &dyn ZoneRules,
) -> Result<Option<Interval>, CursorError> {
    clamp_interval(interval, bounds, rules)
}
