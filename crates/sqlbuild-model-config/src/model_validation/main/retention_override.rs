//! Read a MODEL header's `time_travel_retention` as `resolve_time_travel_retention` does.

use sqlbuild_core::text::models::PythonText;

use crate::errors::ConfigError;
use crate::model_validation::_helpers::config::model_header_help;
use crate::model_validation::_helpers::config::text_if_string;
use crate::model_validation::_helpers::durations::{DurationNumberError, parse_duration};
use crate::model_validation::constants::{DISABLED_RETENTION, INHERIT_POLICY, ZERO_DAY_DURATION};
use crate::model_validation::models::RetentionOverride;
use crate::types::{AuthoredNode, NodeKind};

const RETENTION_KEY: &str = "time_travel_retention";

/// Return the header retention override, or the error it raises.
pub fn retention_override<N: AuthoredNode>(
    python: PythonText,
    value: Option<&N>,
    model_name: &str,
) -> Result<RetentionOverride, ConfigError> {
    let error = |text: String| {
        ConfigError::compile(format!("model '{model_name}': {RETENTION_KEY} {text}"))
    };
    let invalid = |expected: &str| error(format!("must be a whole-day string like {expected}"));
    let Some(value) = value.filter(|node| node.kind() != NodeKind::Null) else {
        return Ok(RetentionOverride::Inherit);
    };
    let Some(text) = text_if_string(value) else {
        return Err(invalid("'7d'"));
    };
    match text.as_str() {
        INHERIT_POLICY => Ok(RetentionOverride::Inherit),
        DISABLED_RETENTION => Ok(RetentionOverride::Unmanaged),
        ZERO_DAY_DURATION => Ok(RetentionOverride::Days(0)),
        _ => match parse_duration(python, &text) {
            Ok(Some(duration)) if duration.is_whole_days() => u64::try_from(duration.days())
                .map(RetentionOverride::Days)
                .map_err(|_| invalid("'7d', 'inherit', or 'disabled'")),
            Ok(_) => Err(invalid("'7d', 'inherit', or 'disabled'")),
            Err(number_error) => {
                let (problem, purpose) = match number_error {
                    DurationNumberError::NonAsciiDigits => (
                        "uses digits outside ASCII",
                        "write time_travel_retention with ASCII digits 0-9",
                    ),
                    DurationNumberError::TooLarge => (
                        "has a number larger than a 64-bit integer",
                        "use a time_travel_retention whose days fit in 64 bits",
                    ),
                };
                Err(ConfigError::compile(format!(
                    "model '{model_name}': {RETENTION_KEY} '{text}' {problem}"
                ))
                .with_help(model_header_help(purpose, &format!("{RETENTION_KEY} '7d'"))))
            }
        },
    }
}
