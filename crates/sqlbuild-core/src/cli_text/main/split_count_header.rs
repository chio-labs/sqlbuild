//! The parts of a `Title (count)` header.

use crate::cli_text::_helpers::summary_text::count_header_parts;

/// The title and the `count)` text, when the header ends with a parenthesized count.
#[must_use]
pub fn split_count_header(text: &str) -> Option<(&str, &str)> {
    count_header_parts(text)
}
