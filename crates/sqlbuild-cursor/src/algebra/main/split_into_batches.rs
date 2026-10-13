//! `split_into_batches`: one cursor interval cut into batches.

use crate::algebra::_helpers::intervals::split_interval;
use crate::algebra::errors::CursorError;
use crate::algebra::models::Interval;
use crate::algebra::types::ZoneRules;

/// Consecutive batches of a positive number of grains; the last ends at the interval's end.
pub fn split_into_batches(
    interval: &Interval,
    step: i64,
    rules: &dyn ZoneRules,
) -> Result<Vec<Interval>, CursorError> {
    split_interval(interval, step, rules)
}
