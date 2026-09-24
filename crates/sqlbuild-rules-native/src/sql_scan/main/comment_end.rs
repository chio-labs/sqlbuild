//! SQL line and block comment boundaries.

use crate::sql_scan::models::Unclosed;

/// Return the end of a line or block comment starting at `index`, if one starts there.
pub(crate) fn comment_end(sql: &[u8], index: usize) -> Result<Option<usize>, Unclosed> {
    match (sql.get(index), sql.get(index + 1)) {
        (Some(b'-'), Some(b'-')) => Ok(Some(
            sql[index + 2..]
                .iter()
                .position(|byte| *byte == b'\n')
                .map_or(sql.len(), |offset| index + 2 + offset + 1),
        )),
        (Some(b'/'), Some(b'*')) => sql[index + 2..]
            .windows(2)
            .position(|pair| pair == b"*/")
            .map(|offset| Some(index + 2 + offset + 2))
            .ok_or(Unclosed::BlockComment),
        _ => Ok(None),
    }
}
