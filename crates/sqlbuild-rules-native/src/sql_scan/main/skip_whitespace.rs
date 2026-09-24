//! Unicode whitespace skipping for SQL scanners.

/// Return the first index at or after `index` that is not Unicode whitespace.
pub(crate) fn skip_whitespace(sql: &str, mut index: usize) -> usize {
    while let Some(character) = sql.get(index..).and_then(|rest| rest.chars().next()) {
        if !character.is_whitespace() {
            break;
        }
        index += character.len_utf8();
    }
    index
}
