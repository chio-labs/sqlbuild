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
        Some(b'$') if policy.dollar_quotes => dollar_quote_end(sql, index),
        _ => Ok(None),
    }
}

/// Return the end of the `$$` or `$tag$` literal opening at `start`, if one opens there.
fn dollar_quote_end(sql: &[u8], start: usize) -> Result<Option<usize>, Unclosed> {
    if start
        .checked_sub(1)
        .is_some_and(|previous| continues_dollar_word(sql[previous]))
    {
        return Ok(None);
    }
    let tag_end = sql[start + 1..]
        .iter()
        .position(|byte| !(byte.is_ascii_alphanumeric() || *byte == b'_'))
        .map_or(sql.len(), |offset| start + 1 + offset);
    let tag = &sql[start + 1..tag_end];
    if sql.get(tag_end) != Some(&b'$') || tag.first().is_some_and(u8::is_ascii_digit) {
        return Ok(None);
    }
    let delimiter = &sql[start..=tag_end];
    sql[tag_end + 1..]
        .windows(delimiter.len())
        .position(|window| window == delimiter)
        .map(|offset| Some(tag_end + 1 + offset + delimiter.len()))
        .ok_or(Unclosed::Quote)
}

fn continues_dollar_word(byte: u8) -> bool {
    !byte.is_ascii() || byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'$')
}
