//! `compare`: the ordering of two compatible cursor values.

use std::cmp::Ordering;

use crate::algebra::_helpers::comparison::compare_scalars;
use crate::algebra::errors::CursorError;
use crate::algebra::models::Scalar;
use crate::algebra::types::ZoneRules;

/// How `left` orders against `right`; integers and temporal values do not compare.
pub fn compare(
    left: &Scalar,
    right: &Scalar,
    rules: &dyn ZoneRules,
) -> Result<Ordering, CursorError> {
    compare_scalars(left, right, rules)
}
