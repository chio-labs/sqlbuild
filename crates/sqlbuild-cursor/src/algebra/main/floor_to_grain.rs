//! `floor_to_grain`: the aligned boundary at or before a cursor value.

use crate::algebra::_helpers::arithmetic::floor_scalar;
use crate::algebra::models::{Grain, Scalar};

/// `value` floored to `grain`; integers and day-or-finer dates come back unchanged.
#[must_use]
pub fn floor_to_grain(value: &Scalar, grain: Option<Grain>) -> Scalar {
    floor_scalar(value, grain)
}
