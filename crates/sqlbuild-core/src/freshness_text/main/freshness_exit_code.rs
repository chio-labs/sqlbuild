//! The exit code of `sqb freshness`.

use crate::freshness_text::_helpers::counts::status_count;
use crate::freshness_text::models::{FreshnessSourceResult, FreshnessStatus};

/// 1 for stale sources under `--fail-on-stale` or failures under `--fail-on-error`, else 0.
#[must_use]
pub fn freshness_exit_code(
    results: &[FreshnessSourceResult],
    (fail_on_stale, fail_on_error): (bool, bool),
) -> i32 {
    let unknown: i64 = status_count(results, FreshnessStatus::Unknown);
    let errors: i64 = status_count(results, FreshnessStatus::Error);
    if fail_on_stale && (status_count(results, FreshnessStatus::Changed) + unknown + errors) > 0 {
        return 1;
    }
    i32::from(fail_on_error && unknown + errors > 0)
}
