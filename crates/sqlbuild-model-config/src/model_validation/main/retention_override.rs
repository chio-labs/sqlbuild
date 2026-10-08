//! Read a MODEL header's `time_travel_retention` as `resolve_time_travel_retention` does.

use crate::model_validation::_helpers::config::optional_text;
use crate::model_validation::_helpers::durations::parse_duration;
use crate::model_validation::constants::{DISABLED_RETENTION, INHERIT_POLICY, ZERO_DAY_DURATION};
use crate::model_validation::models::{Rejected, RetentionOverride};
use crate::types::AuthoredNode;

/// Return the header retention override, or reject a value Python refuses.
pub fn retention_override<N: AuthoredNode>(
    value: Option<&N>,
) -> Result<RetentionOverride, Rejected> {
    let Some(text) = optional_text(value)? else {
        return Ok(RetentionOverride::Inherit);
    };
    match text.as_str() {
        INHERIT_POLICY => Ok(RetentionOverride::Inherit),
        DISABLED_RETENTION => Ok(RetentionOverride::Unmanaged),
        ZERO_DAY_DURATION => Ok(RetentionOverride::Days(0)),
        _ => match parse_duration(&text)? {
            Some(duration) if duration.is_whole_days() => u64::try_from(duration.days())
                .map(RetentionOverride::Days)
                .map_err(|_| Rejected),
            _ => Err(Rejected),
        },
    }
}
