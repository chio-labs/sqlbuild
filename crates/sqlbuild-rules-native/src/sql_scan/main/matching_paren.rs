//! Quote- and comment-aware parenthesis matching.

use crate::sql_scan::main::non_code_end::non_code_end;
use crate::sql_scan::models::{QuotePolicy, Unclosed};

/// Return the index of the parenthesis closing the one at `open`, skipping quotes and comments.
pub(crate) fn matching_paren(
    sql: &[u8],
    open: usize,
    policy: QuotePolicy,
) -> Result<usize, Unclosed> {
    let mut depth = 0isize;
    let mut index = open;
    while index < sql.len() {
        if let Some(end) = non_code_end(sql, index, policy)? {
            index = end;
            continue;
        }
        match sql[index] {
            b'(' => depth += 1,
            b')' => {
                depth -= 1;
                if depth == 0 {
                    return Ok(index);
                }
            }
            _ => {}
        }
        index += 1;
    }
    Err(Unclosed::Parenthesis)
}
