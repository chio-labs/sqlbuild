//! Whether text runs straight on from a closing quote, which means the quote was inside the text.

use crate::header_strings::types::HeaderChar;

/// Whether the unit at `after`, just past a closing quote, continues the text: a letter, digit,
/// underscore or another quote. A value is always followed by space, punctuation or the end.
pub fn run_on_after_close<T: HeaderChar + Into<u32>>(text: &[T], after: usize) -> bool {
    text.get(after).is_some_and(|unit| {
        let code: u32 = (*unit).into();
        char::from_u32(code).is_some_and(|character| {
            character.is_alphanumeric() || matches!(character, '_' | '"' | '\'')
        }) || code >= 0x80
    })
}
