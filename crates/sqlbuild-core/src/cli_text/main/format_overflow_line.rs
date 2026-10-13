//! The hint that a section shows only some of its entries.

use crate::cli_text::_helpers::summary_text::overflow_line;

/// `... and N more (use <flag> to show all)`, dim, when `hidden` entries are not shown.
#[must_use]
pub fn format_overflow_line(hidden: i64, indent: &str, flag: &str) -> Option<String> {
    overflow_line(hidden, indent, flag)
}
