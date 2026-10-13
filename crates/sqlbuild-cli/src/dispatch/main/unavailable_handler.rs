//! The failure of a command whose injected handler set lacks its handler.

use crate::dispatch::models::DispatchFailure;

/// The failure an injected handler set without the route's handler raises.
#[must_use]
pub fn unavailable_handler(command: &str, code: &'static str) -> DispatchFailure {
    DispatchFailure {
        message: format!("{command} command handler is unavailable"),
        code,
        help: None,
    }
}
