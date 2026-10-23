//! Whether a closing `"""` was really inside the text it seemed to end.

use crate::header_strings::constants::TRIPLE_QUOTE_LENGTH;
use crate::header_strings::main::opens_triple_quote::opens_triple_quote;
use crate::header_strings::main::run_on_after_close::run_on_after_close;

/// Whether the `"""` ending at `end` was inside its text: text, or text then `"""`, follows it.
pub fn closes_inside_text<T: Copy + PartialEq + From<u8> + Into<u32>>(
    text: &[T],
    end: usize,
) -> bool {
    if run_on_after_close(text, end) {
        return true;
    }
    let is = |index: usize, byte: u8| text.get(index) == Some(&T::from(byte));
    let mut next: usize = end;
    while is(next, b' ') || is(next, b'\t') || is(next, b'\r') {
        next += 1;
    }
    let separator: bool = next >= text.len()
        || b"\n,)]}:".iter().any(|byte| is(next, *byte))
        || (is(next, b'-') && is(next + 1, b'-'))
        || (is(next, b'/') && is(next + 1, b'*'));
    if separator {
        return false;
    }
    let mut index: usize = next;
    while index + TRIPLE_QUOTE_LENGTH <= text.len() && !is(index, b'\n') {
        if opens_triple_quote(text, index) {
            return true;
        }
        index += 1;
    }
    false
}
