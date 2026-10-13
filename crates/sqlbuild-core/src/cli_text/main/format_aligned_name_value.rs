//! One aligned name/value row.

use crate::cli_text::_helpers::summary_text::aligned_row;
use crate::cli_text::models::AlignedRow;

/// The prefix, the styled name padded on the plain name's width, and the value.
#[must_use]
pub fn format_aligned_name_value(row: &AlignedRow) -> String {
    aligned_row(row)
}
