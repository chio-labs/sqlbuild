//! The exit code of `sqb check`.

use crate::check_command::models::{CheckResultText, CheckStatus};

/// 1 when any check failed, else 0.
#[must_use]
pub fn check_exit_code(results: &[CheckResultText]) -> i32 {
    i32::from(
        results
            .iter()
            .any(|result| result.status == CheckStatus::Fail),
    )
}
