//! The compiler's generic comment and quoted-text rules without dialect information.

use crate::sql_scan::main::comment_end::comment_end;
use crate::sql_scan::main::non_code_end::non_code_end;
use crate::sql_scan::models::{QuotePolicy, Unclosed};

/// Python's generic comment or quoted-text end at `index`; backticks never double, a lone `$` is one character.
pub(crate) fn generic_skip_end(sql: &[u8], index: usize) -> Result<Option<usize>, Unclosed> {
    match sql.get(index) {
        Some(b'`') => sql[index + 1..]
            .iter()
            .position(|byte| *byte == b'`')
            .map(|offset| Some(index + 1 + offset + 1))
            .ok_or(Unclosed::Quote),
        Some(b'$') => Ok(Some(
            non_code_end(sql, index, QuotePolicy::COMPILER)?.unwrap_or(index + 1),
        )),
        _ => match comment_end(sql, index)? {
            Some(end) => Ok(Some(end)),
            None => non_code_end(sql, index, QuotePolicy::COMPILER),
        },
    }
}
