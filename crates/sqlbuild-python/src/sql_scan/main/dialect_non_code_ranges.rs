//! Dialect-aware comment and quoted-text ranges of one SQL text.

use crate::sql_scan::_helpers::dialect::non_code_ranges;
use crate::sql_scan::models::LexicalSyntax;

/// Return every comment and quoted-text range in `sql`; an unclosed one extends to the end.
pub(crate) fn dialect_non_code_ranges(sql: &str, syntax: &LexicalSyntax) -> Vec<(usize, usize)> {
    non_code_ranges(sql, syntax)
}
