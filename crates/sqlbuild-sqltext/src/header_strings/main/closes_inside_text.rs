//! Whether a closing `"""` was really inside the text it seemed to end.

use crate::header_strings::_helpers::separators::{run_on_after_close, separator_follows};
use crate::header_strings::constants::TRIPLE_QUOTE_LENGTH;
use crate::header_strings::main::opens_triple_quote::opens_triple_quote;

/// Whether the `"""` ending at `end` was inside its text: text, or text then `"""`, follows it.
pub fn closes_inside_text<T: Copy + PartialEq + From<u8> + Into<u32>>(
    text: &[T],
    end: usize,
) -> bool {
    if run_on_after_close(text, end) {
        return true;
    }
    if separator_follows(text, end) {
        return false;
    }
    let is = |index: usize, byte: u8| text.get(index) == Some(&T::from(byte));
    let mut index: usize = end;
    while index + TRIPLE_QUOTE_LENGTH <= text.len() && !is(index, b'\n') {
        if opens_triple_quote(text, index) {
            return true;
        }
        index += 1;
    }
    false
}
