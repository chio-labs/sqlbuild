//! `age_status`: an observed timestamp's age against its warn and error thresholds.

use sqlbuild_cursor::algebra::models::LocalDateTime;

use crate::freshness::_helpers::durations::single_unit_seconds;
use crate::freshness::_helpers::moments::elapsed_micros;
use crate::freshness::constants::{AGE_POLICY_INVALID, MICROS_PER_SECOND};
use crate::freshness::errors::FreshnessError;
use crate::freshness::models::AgeStatus;

/// Whether `age_seconds > threshold`, as Python compares a float with an integer.
fn older_than(age_micros: i128, threshold: &str) -> Result<bool, FreshnessError> {
    let Some(seconds) = single_unit_seconds(threshold) else {
        return Err(FreshnessError::Input(AGE_POLICY_INVALID.to_owned()));
    };
    let Some(seconds) = seconds else {
        return Ok(false);
    };
    let age_seconds: f64 = age_micros as f64 / MICROS_PER_SECOND as f64;
    Ok(age_seconds > seconds as f64)
}

/// The data version's age at `observed_at`: `error` past `error_after`, else `warn` past `warn_after`, else `pass`.
pub fn age_status(
    (data_version, observed_at): (&LocalDateTime, &LocalDateTime),
    error_after: Option<&str>,
    warn_after: Option<&str>,
) -> Result<AgeStatus, FreshnessError> {
    let age_micros: i128 = elapsed_micros(data_version, observed_at);
    if let Some(threshold) = error_after
        && older_than(age_micros, threshold)?
    {
        return Ok(AgeStatus::Error);
    }
    if let Some(threshold) = warn_after
        && older_than(age_micros, threshold)?
    {
        return Ok(AgeStatus::Warn);
    }
    Ok(AgeStatus::Pass)
}
