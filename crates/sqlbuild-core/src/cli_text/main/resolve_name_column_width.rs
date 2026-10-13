//! The left column width of aligned name/value rows.

use crate::cli_text::_helpers::summary_text::name_column_width;

/// The longest name's width, at least `min_width`.
#[must_use]
pub fn resolve_name_column_width(names: &[String], min_width: usize) -> usize {
    name_column_width(names, min_width)
}
