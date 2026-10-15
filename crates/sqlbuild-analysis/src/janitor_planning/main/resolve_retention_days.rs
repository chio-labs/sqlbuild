//! Effective janitor relation retention.

use crate::janitor_planning::constants::DEFAULT_RETENTION_DAYS;

/// The CLI override, else the configured days, else the default.
#[must_use]
pub fn resolve_retention_days(override_days: Option<i64>, configured: Option<i64>) -> i64 {
    override_days
        .or(configured)
        .unwrap_or(DEFAULT_RETENTION_DAYS)
}
