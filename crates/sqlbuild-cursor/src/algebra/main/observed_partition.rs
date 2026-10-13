//! `observed_partition`: the canonical partition containing an observed cursor value.

use crate::algebra::_helpers::intervals::observed_partition_value;
use crate::algebra::errors::CursorError;
use crate::algebra::models::{Grain, Interval, Scalar};

/// The grain-wide interval holding `value`; an integer's partition is the next integer.
pub fn observed_partition(value: &Scalar, grain: Option<Grain>) -> Result<Interval, CursorError> {
    observed_partition_value(value, grain)
}
