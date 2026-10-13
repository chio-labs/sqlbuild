//! A count with its noun.

use crate::cli_text::_helpers::summary_text::count_noun;

/// The count with the singular noun for one and the plural (default `<singular>s`) otherwise.
#[must_use]
pub fn format_count_noun(count: i64, singular: &str, plural: Option<&str>) -> String {
    count_noun(count, singular, plural)
}
