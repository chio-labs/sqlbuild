//! How a failed command is reported: its fallback code and debug log message.

use crate::dispatch::models::CommandFailure;

/// `(fallback code, log message)` of a failure kind.
#[must_use]
pub fn failure_report(failure: CommandFailure) -> (&'static str, &'static str) {
    match failure {
        CommandFailure::User => ("C000", "cli user error"),
        CommandFailure::Lint => ("L001", "lint failed"),
        CommandFailure::Command => ("E001", "command failed"),
    }
}
