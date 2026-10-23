//! What may follow a header value: a separator, a comment or the end of its line, not more text.

use crate::header_strings::constants::FIRST_NON_ASCII;

/// Whether a separator, comment, line end or the end of `text` follows `after`, past spaces.
pub(crate) fn separator_follows<T: Copy + PartialEq + From<u8>>(text: &[T], after: usize) -> bool {
    let is = |index: usize, byte: u8| text.get(index) == Some(&T::from(byte));
    let mut next: usize = after;
    while is(next, b' ') || is(next, b'\t') || is(next, b'\r') {
        next += 1;
    }
    next >= text.len()
        || b"\n,)]}:".iter().any(|byte| is(next, *byte))
        || (is(next, b'-') && is(next + 1, b'-'))
        || (is(next, b'/') && is(next + 1, b'*'))
}

/// Whether the unit at `after`, just past a closing quote, is a word character or another quote.
pub(crate) fn run_on_after_close<T: Copy + PartialEq + From<u8> + Into<u32>>(
    text: &[T],
    after: usize,
) -> bool {
    text.get(after).is_some_and(|unit| {
        let code: u32 = (*unit).into();
        char::from_u32(code).is_some_and(|character| {
            character.is_alphanumeric() || matches!(character, '_' | '"' | '\'')
        }) || code >= FIRST_NON_ASCII
    })
}
