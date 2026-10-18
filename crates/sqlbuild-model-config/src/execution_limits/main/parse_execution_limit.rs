//! Parse a per-item execution limit such as `30s`, `10m` or `disabled`.

use crate::execution_limits::constants::DISABLED_LIMIT;
use crate::execution_limits::models::ExecutionLimit;
use crate::model_validation::main::fixed_duration_seconds::fixed_duration_seconds;

/// The limit `text` spells, or `None` when it is not a positive fixed duration or `disabled`.
#[must_use]
pub fn parse_execution_limit(text: &str) -> Option<ExecutionLimit> {
    let text = text.trim();
    if text == DISABLED_LIMIT {
        return Some(ExecutionLimit::Disabled);
    }
    match u64::try_from(fixed_duration_seconds(text)?) {
        Ok(seconds) if seconds > 0 => Some(ExecutionLimit::Seconds(seconds)),
        Ok(_) | Err(_) => None,
    }
}
