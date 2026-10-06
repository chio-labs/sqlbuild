//! Dollar-quoted literal boundaries shared by every scanning policy.

use crate::sql_scan::models::Unclosed;

/// Return the end of the `$$` or `$tag$` literal opening at `start`, if one opens there.
pub(crate) fn dollar_quote_end(sql: &[u8], start: usize) -> Result<Option<usize>, Unclosed> {
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

pub(crate) fn continues_dollar_word(byte: u8) -> bool {
    !byte.is_ascii() || byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'$')
}
