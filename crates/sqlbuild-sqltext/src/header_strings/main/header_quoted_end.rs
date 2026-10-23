//! The extent of one quoted header string, for scanners that only need where it ends.

use crate::header_strings::constants::TRIPLE_QUOTE_LENGTH;
use crate::header_strings::errors::TripleQuoteError;
use crate::header_strings::main::follows_description_key::follows_description_key;
use crate::header_strings::main::opens_triple_quote::opens_triple_quote;
use crate::header_strings::main::prose_end::prose_end;
use crate::header_strings::main::triple_quoted_end::triple_quoted_end;

/// The offset just past the header string opening at `start`, or `None` when it never closes.
pub fn header_quoted_end<T: Copy + PartialEq + From<u8> + Into<u32>>(
    text: &[T],
    start: usize,
) -> Option<usize> {
    if follows_description_key(text, start)
        && let Ok(end) = prose_end(text, start)
    {
        return Some(end);
    }
    if opens_triple_quote(text, start) {
        return match triple_quoted_end(text, start) {
            Ok((_, end)) => Some(end),
            Err(TripleQuoteError::Inside(index)) => Some(index + TRIPLE_QUOTE_LENGTH),
            Err(TripleQuoteError::Unclosed) => None,
        };
    }
    let quote: T = text[start];
    let mut index: usize = start + 1;
    while index < text.len() {
        if text[index] == T::from(b'\\') {
            index += 2;
            continue;
        }
        if text[index] == quote {
            return Some(index + 1);
        }
        index += 1;
    }
    None
}
