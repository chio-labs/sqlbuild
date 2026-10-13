//! `exclusive_end_from_observed_max`: availability derived from an observed cursor maximum.

use crate::algebra::_helpers::intervals::observed_partition_value;
use crate::algebra::errors::CursorError;
use crate::algebra::main::validate_interval::validate_interval;
use crate::algebra::models::{Grain, Interval, Scalar};
use crate::algebra::types::ZoneRules;

/// The end of the validated partition holding the observed maximum `value`.
pub fn exclusive_end_from_observed_max(
    value: &Scalar,
    grain: Option<Grain>,
    rules: &dyn ZoneRules,
) -> Result<Scalar, CursorError> {
    let partition: Interval = observed_partition_value(value, grain)?;
    validate_interval(&partition, rules)?;
    Ok(partition.end)
}
