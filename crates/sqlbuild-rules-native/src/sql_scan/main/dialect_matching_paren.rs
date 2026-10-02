//! Dialect-aware parenthesis matching.

use crate::sql_scan::_helpers::dialect::matching_paren;
use crate::sql_scan::models::{LexicalSyntax, Unclosed};

/// Return the index of the parenthesis closing the one at `open` under the dialect's rules.
pub(crate) fn dialect_matching_paren(
    sql: &[u8],
    open: usize,
    syntax: &LexicalSyntax,
) -> Result<usize, Unclosed> {
    matching_paren(sql, open, syntax)
}
