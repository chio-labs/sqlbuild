//! The target duration limit against the adapter.

use crate::build_command::constants::{
    DEFAULT_TARGET_LABEL, DURATION_EXCEEDED_CODE, DURATION_UNSUPPORTED_CODE,
};
use crate::build_command::errors::BuildCommandError;
use crate::build_command::models::DurationLimit;

/// The refusal when the adapter cannot enforce the target's `max_duration`.
#[must_use]
pub fn duration_limit_error(limit: &DurationLimit) -> Option<BuildCommandError> {
    let target: &str = limit.target_name.as_deref().unwrap_or(DEFAULT_TARGET_LABEL);
    let adapter: &str = &limit.adapter_name;
    let Some(maximum) = limit.adapter_limit_seconds else {
        return limit.configures_max_duration.then(|| {
            BuildCommandError::new(
                Some(DURATION_UNSUPPORTED_CODE),
                format!(
                    "Target '{target}' configures max_duration, but adapter '{adapter}' cannot cancel active statements safely"
                ),
                limit.remediation.as_deref(),
            )
        });
    };
    let seconds: i64 = limit.max_duration_seconds?;
    (seconds > maximum).then(|| {
        BuildCommandError::new(
            Some(DURATION_EXCEEDED_CODE),
            format!(
                "Target '{target}' max_duration exceeds the largest duration supported by adapter '{adapter}' ({maximum} seconds)"
            ),
            limit.remediation.as_deref(),
        )
    })
}
