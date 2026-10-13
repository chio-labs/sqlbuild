//! The summary footer of a command's counts.

use crate::cli_text::_helpers::summary_text::summary_footer;
use crate::cli_text::models::{CliStyle, SummaryCount};

/// `LABEL=value` pairs coloured by outcome, then the elapsed time when given.
#[must_use]
pub fn format_summary_footer(
    style: CliStyle,
    counts: &[SummaryCount],
    elapsed: Option<&str>,
) -> String {
    summary_footer(style, counts, elapsed)
}
