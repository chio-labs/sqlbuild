//! `next_boundary`: the boundary one grain after an aligned cursor value.

use crate::algebra::_helpers::arithmetic::advance_scalar;
use crate::algebra::errors::CursorError;
use crate::algebra::models::{Grain, Scalar};

/// `value` advanced by one `grain`.
pub fn next_boundary(value: &Scalar, grain: Option<Grain>) -> Result<Scalar, CursorError> {
    advance_scalar(value, grain)
}
