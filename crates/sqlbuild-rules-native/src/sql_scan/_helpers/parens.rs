//! Parenthesis matching shared by every scanning policy.

use crate::sql_scan::models::Unclosed;

/// Return the index of the parenthesis closing the one at `open`, skipping non-code spans.
pub(crate) fn matching_paren_with(
    sql: &[u8],
    open: usize,
    non_code_end: impl Fn(&[u8], usize) -> Result<Option<usize>, Unclosed>,
) -> Result<usize, Unclosed> {
    let mut depth = 0isize;
    let mut index = open;
    while index < sql.len() {
        if let Some(end) = non_code_end(sql, index)? {
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
