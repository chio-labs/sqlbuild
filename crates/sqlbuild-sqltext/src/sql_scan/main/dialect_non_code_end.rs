//! Dialect-aware boundaries of the comment or quoted text starting at one offset.

use crate::sql_scan::_helpers::dialect::non_code_end;
use crate::sql_scan::models::{LexicalSyntax, Unclosed};

/// Return the end of a comment or quoted text starting at `index` under the dialect's rules.
pub fn dialect_non_code_end(
    sql: &[u8],
    index: usize,
    syntax: &LexicalSyntax,
) -> Result<Option<usize>, Unclosed> {
    non_code_end(sql, index, syntax)
}
