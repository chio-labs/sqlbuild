//! How many examples a diff shows per column or side when not set explicitly.

use crate::diff_report::constants::{DEFAULT_EXAMPLES, VERBOSE_EXAMPLES};

/// The explicit limit, else ten when verbose and three otherwise.
#[must_use]
pub fn effective_max_examples(explicit: Option<i64>, verbose: bool) -> i64 {
    explicit.unwrap_or(if verbose {
        VERBOSE_EXAMPLES
    } else {
        DEFAULT_EXAMPLES
    })
}
