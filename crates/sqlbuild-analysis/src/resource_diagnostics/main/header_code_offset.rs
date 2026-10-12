//! Where a SQL-authored file's statement header starts.

use crate::resource_diagnostics::constants::{
    BLOCK_COMMENT_END, BLOCK_COMMENT_START, LINE_COMMENT_START, UNCLOSED_BLOCK_COMMENT,
};

/// The code-point offset of the first code after leading whitespace and comments.
pub fn header_code_offset(contents: &str) -> Result<usize, &'static str> {
    let mut rest: &str = contents;
    loop {
        rest = rest.trim_start_matches(char::is_whitespace);
        if let Some(comment) = rest.strip_prefix(LINE_COMMENT_START) {
            rest = comment.find('\n').map_or("", |end| &comment[end + 1..]);
        } else if rest.starts_with(BLOCK_COMMENT_START) {
            let end: usize = rest[BLOCK_COMMENT_START.len()..]
                .find(BLOCK_COMMENT_END)
                .ok_or(UNCLOSED_BLOCK_COMMENT)?;
            rest = &rest[BLOCK_COMMENT_START.len() + end + BLOCK_COMMENT_END.len()..];
        } else {
            return Ok(contents.chars().count() - rest.chars().count());
        }
    }
}
