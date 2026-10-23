//! Where a prose header string ends, by the quoting rules of prose.

use crate::header_strings::_helpers::prose_ends::{double_end, single_end, triple_end};
use crate::header_strings::errors::ProseError;
use crate::header_strings::main::opens_triple_quote::opens_triple_quote;

/// The offset just past the prose string opening at `start`, or why it does not end well.
pub fn prose_end<T: Copy + PartialEq + From<u8> + Into<u32>>(
    text: &[T],
    start: usize,
) -> Result<usize, ProseError> {
    if opens_triple_quote(text, start) {
        return triple_end(text, start);
    }
    if text[start] == T::from(b'"') {
        return double_end(text, start);
    }
    single_end(text, start)
}
