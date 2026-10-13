//! The target model-count limit.

use crate::build_command::constants::{DEFAULT_TARGET_LABEL, MODEL_LIMIT_CODE};
use crate::build_command::errors::BuildCommandError;
use crate::build_command::models::ModelLimit;

/// The refusal when `model_count` exceeds the target's `max_models`.
#[must_use]
pub fn model_limit_error(
    model_count: usize,
    limit: &ModelLimit,
    refusal_note: &str,
) -> Option<BuildCommandError> {
    let maximum: i64 = limit.max_models?;
    if i64::try_from(model_count).is_ok_and(|count| count <= maximum) {
        return None;
    }
    let target: &str = limit.target_name.as_deref().unwrap_or(DEFAULT_TARGET_LABEL);
    Some(BuildCommandError::new(
        Some(MODEL_LIMIT_CODE),
        format!(
            "Build plan exceeds the configured model limit\n\nTarget:          {target}\nSelected models: {model_count}\nMaximum models:  {maximum}\nConfiguration:   targets.{target}.execution_limits.max_models\n\n{refusal_note}"
        ),
        limit.remediation.as_deref(),
    ))
}
