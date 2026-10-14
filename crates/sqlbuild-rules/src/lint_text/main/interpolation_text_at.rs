//! `interpolation_text_at`: the interpolation token beginning at one character offset.

use crate::lint_text::_helpers::sites::{byte_offset, lint_policy, site_end};
use crate::sql_lint::main::backtick_identifiers::backtick_identifiers;

/// Return the interpolation token starting at character position `start`, if there is one.
pub fn interpolation_text_at(body: &str, start: usize, dialect: &str) -> Option<String> {
    let byte_start: usize = byte_offset(body, start)?;
    let end: usize = site_end(body, byte_start, lint_policy(backtick_identifiers(dialect)))?;
    Some(body[byte_start..end].to_string())
}
