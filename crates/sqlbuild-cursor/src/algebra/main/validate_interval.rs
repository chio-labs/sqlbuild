//! `validate_interval`: the checks an aligned interval must pass when it is built.

use crate::algebra::_helpers::arithmetic::floor_scalar;
use crate::algebra::_helpers::comparison::compare_scalars;
use crate::algebra::_helpers::failures::algebra;
use crate::algebra::constants::{
    END_NOT_ALIGNED, START_NOT_ALIGNED, START_NOT_BEFORE_END, TEMPORAL_INTERVALS_NEED_GRAIN,
};
use crate::algebra::errors::CursorError;
use crate::algebra::models::{Interval, Scalar, ScalarValue};
use crate::algebra::types::ZoneRules;

/// Whether two values of one kind are equal as `datetime` equality in one zone reads them.
fn same_value(left: &Scalar, right: &Scalar) -> bool {
    match (&left.value, &right.value) {
        (ScalarValue::Timestamp(left), ScalarValue::Timestamp(right)) => left.local == right.local,
        (left, right) => left == right,
    }
}

/// An ordered interval whose temporal ends carry a grain and sit on its boundaries.
pub fn validate_interval(interval: &Interval, rules: &dyn ZoneRules) -> Result<(), CursorError> {
    if compare_scalars(&interval.start, &interval.end, rules)?.is_ge() {
        return Err(algebra(START_NOT_BEFORE_END));
    }
    let Some(grain) = interval.grain else {
        let integral: bool = matches!(interval.start.value, ScalarValue::Integer(_))
            && matches!(interval.end.value, ScalarValue::Integer(_));
        return if integral {
            Ok(())
        } else {
            Err(algebra(TEMPORAL_INTERVALS_NEED_GRAIN))
        };
    };
    if !same_value(&floor_scalar(&interval.start, Some(grain)), &interval.start) {
        return Err(algebra(START_NOT_ALIGNED));
    }
    if !same_value(&floor_scalar(&interval.end, Some(grain)), &interval.end) {
        return Err(algebra(END_NOT_ALIGNED));
    }
    Ok(())
}
