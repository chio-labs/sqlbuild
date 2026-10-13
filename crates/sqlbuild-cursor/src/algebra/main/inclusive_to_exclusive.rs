//! `inclusive_to_exclusive`: an operator-declared inclusive bound as an exclusive one.

use crate::algebra::_helpers::arithmetic::shift_bound;
use crate::algebra::constants::TEMPORAL_BOUNDS_NEED_GRAIN;
use crate::algebra::errors::CursorError;
use crate::algebra::models::{Grain, Scalar};

/// `value` advanced by one cursor unit: one, a day, or the grain's fixed step.
pub fn inclusive_to_exclusive(value: &Scalar, grain: Option<Grain>) -> Result<Scalar, CursorError> {
    shift_bound(value, grain, 1, TEMPORAL_BOUNDS_NEED_GRAIN)
}
