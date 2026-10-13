//! Result counts of one load run.

use crate::load_command::models::{LoadCounts, LoadResultText, LoadStatus};

fn count(results: &[LoadResultText], predicate: impl Fn(&LoadResultText) -> bool) -> i64 {
    i64::try_from(results.iter().filter(|result| predicate(result)).count()).unwrap_or(i64::MAX)
}

/// Successes without warnings pass; successes with warnings warn; failures and skips count apart.
#[must_use]
pub fn load_counts(results: &[LoadResultText]) -> LoadCounts {
    let success = |result: &LoadResultText| result.status == LoadStatus::Success;
    LoadCounts {
        pass: count(results, |result| {
            success(result) && result.warning_messages.is_empty()
        }),
        warn: count(results, |result| {
            success(result) && !result.warning_messages.is_empty()
        }),
        fail: count(results, |result| result.status == LoadStatus::Failed),
        skip: count(results, |result| result.status == LoadStatus::Skipped),
        total: count(results, |_| true),
    }
}
