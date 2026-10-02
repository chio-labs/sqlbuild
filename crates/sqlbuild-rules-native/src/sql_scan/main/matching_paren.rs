//! Quote- and comment-aware parenthesis matching.

use crate::sql_scan::_helpers::parens::matching_paren_with;
use crate::sql_scan::main::non_code_end::non_code_end;
use crate::sql_scan::models::{QuotePolicy, Unclosed};

/// Return the index of the parenthesis closing the one at `open`, skipping quotes and comments.
pub(crate) fn matching_paren(
    sql: &[u8],
    open: usize,
    policy: QuotePolicy,
) -> Result<usize, Unclosed> {
    matching_paren_with(sql, open, |sql, index| non_code_end(sql, index, policy))
}
