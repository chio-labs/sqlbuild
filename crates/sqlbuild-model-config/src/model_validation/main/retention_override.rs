//! Read a MODEL header's `time_travel_retention` as `resolve_time_travel_retention` does.

use crate::errors::ConfigError;
use crate::model_validation::_helpers::config::text_if_string;
use crate::model_validation::_helpers::durations::parse_duration;
use crate::model_validation::constants::{DISABLED_RETENTION, INHERIT_POLICY, ZERO_DAY_DURATION};
use crate::model_validation::models::{RetentionOverride, ValidationStop};
use crate::types::{AuthoredNode, NodeKind};

/// Return the header retention override, the error Python raises, or a deferral.
pub fn retention_override<N: AuthoredNode>(
    value: Option<&N>,
    model_name: &str,
) -> Result<RetentionOverride, ValidationStop> {
    let invalid = |expected: &str| {
        ValidationStop::Error(ConfigError::compile(format!(
            "model '{model_name}': time_travel_retention must be a whole-day string like {expected}"
        )))
    };
    let Some(value) = value.filter(|node| node.kind() != NodeKind::Null) else {
        return Ok(RetentionOverride::Inherit);
    };
    let Some(text) = text_if_string(value)? else {
        return Err(invalid("'7d'"));
    };
    match text.as_str() {
        INHERIT_POLICY => Ok(RetentionOverride::Inherit),
        DISABLED_RETENTION => Ok(RetentionOverride::Unmanaged),
        ZERO_DAY_DURATION => Ok(RetentionOverride::Days(0)),
        _ => match parse_duration(&text)? {
            Some(duration) if duration.is_whole_days() => u64::try_from(duration.days())
                .map(RetentionOverride::Days)
                .map_err(|_| ValidationStop::Defer),
            _ => Err(invalid("'7d', 'inherit', or 'disabled'")),
        },
    }
}
