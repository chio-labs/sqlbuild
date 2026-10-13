//! The code-owned remediation of each semantic diagnostic code.

use crate::semantic_checks::constants::SEMANTIC_HELP;

/// Each semantic diagnostic code and its help, in catalogue order.
#[must_use]
pub fn semantic_help_catalogue() -> &'static [(&'static str, &'static str)] {
    SEMANTIC_HELP
}
