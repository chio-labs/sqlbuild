//! `third_party_console_form`: how a non-debug console shows a third-party record.

use crate::diagnostic_routing::constants::{LEVEL_ERROR, LEVEL_WARNING};
use crate::diagnostic_routing::models::ThirdPartyConsoleForm;

/// Errors in full, warnings as one line, and nothing below warning.
#[must_use]
pub fn third_party_console_form(level: i64) -> ThirdPartyConsoleForm {
    if level >= LEVEL_ERROR {
        ThirdPartyConsoleForm::Full
    } else if level >= LEVEL_WARNING {
        ThirdPartyConsoleForm::Summary
    } else {
        ThirdPartyConsoleForm::Hidden
    }
}
