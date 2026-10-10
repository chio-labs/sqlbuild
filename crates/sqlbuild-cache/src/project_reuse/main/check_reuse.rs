use crate::project_reuse::models::{ReuseAttempt, ReuseCheck};

/// The reuse attempt, or `None` when the project cannot be walked natively.
pub fn check_reuse(check: ReuseCheck<'_>) -> Option<ReuseAttempt> {
    crate::project_reuse::_helpers::attempt::check(check)
}
