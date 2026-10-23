//! Whether text runs straight on from a closing quote, which means the quote was inside the text.

use crate::header_strings::constants::FIRST_NON_ASCII;

/// Whether the unit at `after`, just past a closing quote, is a word character or another quote.
pub fn run_on_after_close<T: Copy + PartialEq + From<u8> + Into<u32>>(
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
