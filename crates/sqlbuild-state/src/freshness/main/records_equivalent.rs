//! `records_equivalent`: whether two freshness records let a source be skipped.

use sqlbuild_cursor::algebra::models::LocalDateTime;

use crate::freshness::_helpers::durations::single_unit_seconds;
use crate::freshness::_helpers::moments::elapsed_micros;
use crate::freshness::constants::{
    C_INT_OVERFLOW, LAG_TOLERANCE_INVALID, MAX_C_INT, MAX_TIMEDELTA_DAYS, MICROS_PER_SECOND,
    SECONDS_PER_DAY, TIMESTAMP_VALUE_KIND,
};
use crate::freshness::errors::FreshnessError;
use crate::freshness::models::ComparableRecord;
use crate::freshness::types::TimestampParser;

/// `timedelta(seconds=...)` of a lag tolerance in microseconds, failing as Python does.
fn tolerance_micros(text: &str) -> Result<u128, FreshnessError> {
    let Some(seconds) = single_unit_seconds(text) else {
        return Err(FreshnessError::Observation(
            LAG_TOLERANCE_INVALID.to_owned(),
        ));
    };
    let days: Option<u128> = seconds.map(|seconds| seconds / SECONDS_PER_DAY);
    match (seconds, days) {
        (Some(seconds), Some(days)) if days <= MAX_TIMEDELTA_DAYS => {
            Ok(seconds * MICROS_PER_SECOND)
        }
        (_, Some(days)) if days <= MAX_C_INT => Err(FreshnessError::Overflow(format!(
            "days={days}; must have magnitude <= {MAX_TIMEDELTA_DAYS}"
        ))),
        _ => Err(FreshnessError::Overflow(C_INT_OVERFLOW.to_owned())),
    }
}

/// Equal hashes, or equal timestamps, or a later timestamp within `lag_tolerance`.
pub fn records_equivalent(
    (previous, current): (&ComparableRecord, &ComparableRecord),
    lag_tolerance: Option<&str>,
    parser: &dyn TimestampParser,
) -> Result<bool, FreshnessError> {
    if previous.data_version_hash == current.data_version_hash {
        return Ok(true);
    }
    if previous.value_kind != TIMESTAMP_VALUE_KIND || current.value_kind != TIMESTAMP_VALUE_KIND {
        return Ok(false);
    }
    let (Some(previous_text), Some(current_text)) = (&previous.data_version, &current.data_version)
    else {
        return Ok(false);
    };
    let previous_time: LocalDateTime = parser.utc_timestamp(previous_text)?;
    let current_time: LocalDateTime = parser.utc_timestamp(current_text)?;
    let elapsed: i128 = elapsed_micros(&previous_time, &current_time);
    if elapsed == 0 {
        return Ok(true);
    }
    let Some(tolerance) = lag_tolerance else {
        return Ok(false);
    };
    if elapsed < 0 {
        return Ok(false);
    }
    Ok(elapsed.unsigned_abs() <= tolerance_micros(tolerance)?)
}
