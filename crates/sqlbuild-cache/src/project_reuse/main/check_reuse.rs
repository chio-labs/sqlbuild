use crate::project_reuse::models::{ReuseAttempt, ReuseCheck};

/// Replay the stored compile when every input matches, otherwise prepare to store one.
pub fn check_reuse(check: ReuseCheck<'_>) -> ReuseAttempt {
    crate::project_reuse::_helpers::attempt::check(check)
}
