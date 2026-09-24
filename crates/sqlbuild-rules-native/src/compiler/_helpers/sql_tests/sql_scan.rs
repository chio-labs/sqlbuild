//! Quote- and comment-aware SQL scanning shared by SQL-test extraction and planning.

/// The SQL construct a scan reached the end of input inside.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Unclosed {
    BlockComment,
    Quote,
    Parenthesis,
}

/// Return the first index at or after `index` that is not whitespace.
pub(crate) fn skip_whitespace(sql: &str, mut index: usize) -> usize {
    while let Some(character) = sql.get(index..).and_then(|rest| rest.chars().next()) {
        if !character.is_whitespace() {
            break;
        }
        index += character.len_utf8();
    }
    index
}

/// Return the end of a line or block comment starting at `index`, if one starts there.
pub(crate) fn comment_end(sql: &str, index: usize) -> Result<Option<usize>, Unclosed> {
    let bytes = sql.as_bytes();
    match (bytes.get(index), bytes.get(index + 1)) {
        (Some(b'-'), Some(b'-')) => Ok(Some(
            sql[index..]
                .find('\n')
                .map_or(sql.len(), |offset| index + offset + 1),
        )),
        (Some(b'/'), Some(b'*')) => sql[index + 2..]
            .find("*/")
            .map(|offset| Some(index + 2 + offset + 2))
            .ok_or(Unclosed::BlockComment),
        _ => Ok(None),
    }
}

/// Return the index after the quoted text starting at `start`, treating doubled quotes as escapes.
pub(crate) fn quoted_end(sql: &str, start: usize) -> Result<usize, Unclosed> {
    let bytes = sql.as_bytes();
    let quote = bytes[start];
    let mut index = start + 1;
    while index < bytes.len() {
        if bytes[index] != quote {
            index += 1;
        } else if bytes.get(index + 1) == Some(&quote) {
            index += 2;
        } else {
            return Ok(index + 1);
        }
    }
    Err(Unclosed::Quote)
}

/// Return the index of the parenthesis closing the one at `open`, skipping quotes and comments.
pub(crate) fn matching_paren(sql: &str, open: usize) -> Result<usize, Unclosed> {
    let bytes = sql.as_bytes();
    let mut depth = 0usize;
    let mut index = open;
    while index < bytes.len() {
        if let Some(end) = comment_end(sql, index)? {
            index = end;
            continue;
        }
        match bytes[index] {
            b'\'' | b'"' | b'`' => {
                index = quoted_end(sql, index)?;
                continue;
            }
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
