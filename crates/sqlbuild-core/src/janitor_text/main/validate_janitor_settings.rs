//! Validate effective janitor retention settings.

use crate::janitor_text::errors::JanitorSettingsError;

/// Reject negative retention or direct state history settings.
pub fn validate_janitor_settings(
    retention_days: i64,
    direct_state_history_versions: i64,
) -> Result<(), JanitorSettingsError> {
    if retention_days < 0 {
        return Err(JanitorSettingsError {
            code: "C501",
            message: "janitor --retention-days must be >= 0",
        });
    }
    if direct_state_history_versions < 0 {
        return Err(JanitorSettingsError {
            code: "C502",
            message: "janitor --direct-state-history-versions must be >= 0",
        });
    }
    Ok(())
}
