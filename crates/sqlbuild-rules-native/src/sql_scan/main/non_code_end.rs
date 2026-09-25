//! Boundaries of the comment or quoted text starting at one offset.

use crate::sql_scan::main::comment_end::comment_end;
use crate::sql_scan::main::quote_end::quote_end;
use crate::sql_scan::models::{QuotePolicy, Unclosed};

/// Return the end of a comment or quoted text starting at `index`, if one starts there.
pub(crate) fn non_code_end(
    sql: &[u8],
    index: usize,
    policy: QuotePolicy,
) -> Result<Option<usize>, Unclosed> {
    if let Some(end) = comment_end(sql, index)? {
        return Ok(Some(end));
    }
    match sql.get(index) {
        Some(byte) if policy.is_quote(*byte) => quote_end(sql, index, policy).map(Some),
        _ => Ok(None),
    }
}
