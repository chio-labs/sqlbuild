//! Boundaries of the comment or quoted text starting at one offset.

use crate::sql_scan::_helpers::dollar::dollar_quote_end;
use crate::sql_scan::main::comment_end::comment_end;
use crate::sql_scan::main::quote_end::quote_end;
use crate::sql_scan::models::{QuotePolicy, Unclosed};

/// Return the end of a comment or quoted text starting at `index`, if one starts there.
#[inline]
pub fn non_code_end(
    sql: &[u8],
    index: usize,
    policy: QuotePolicy,
) -> Result<Option<usize>, Unclosed> {
    match sql.get(index) {
        Some(b'-' | b'/') => comment_end(sql, index),
        Some(b'\'' | b'"') => quote_end(sql, index, policy).map(Some),
        Some(b'`') if policy.backtick_identifiers => quote_end(sql, index, policy).map(Some),
        Some(b'$') if policy.dollar_quotes => dollar_quote_end(sql, index),
        _ => Ok(None),
    }
}
