//! `merge`: overlapping or adjacent cursor intervals joined.

use crate::algebra::_helpers::intervals::merge_interval_values;
use crate::algebra::errors::CursorError;
use crate::algebra::models::Interval;
use crate::algebra::types::ZoneRules;

/// The intervals ordered by start with every overlapping or touching run joined.
pub fn merge(intervals: &[Interval], rules: &dyn ZoneRules) -> Result<Vec<Interval>, CursorError> {
    merge_interval_values(intervals, rules)
}
