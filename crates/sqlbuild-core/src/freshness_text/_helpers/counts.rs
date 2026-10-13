//! Status counts of a freshness run.

use crate::freshness_text::models::{FreshnessSourceResult, FreshnessStatus};

/// Sources with `status`.
pub(crate) fn status_count(results: &[FreshnessSourceResult], status: FreshnessStatus) -> i64 {
    let count: usize = results
        .iter()
        .filter(|result| result.status == status)
        .count();
    i64::try_from(count).unwrap_or(i64::MAX)
}

/// Sources whose age policy evaluated to `age_status`.
pub(crate) fn age_count(results: &[FreshnessSourceResult], age_status: &str) -> i64 {
    let count: usize = results
        .iter()
        .filter(|result| result.age_status.as_deref() == Some(age_status))
        .count();
    i64::try_from(count).unwrap_or(i64::MAX)
}
