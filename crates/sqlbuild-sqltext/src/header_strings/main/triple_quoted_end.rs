//! Where a triple-quoted header string's text and closing delimiter end.

use crate::header_strings::constants::{LONGEST_CLOSING_RUN, TRIPLE_QUOTE_LENGTH};
use crate::header_strings::errors::TripleQuoteError;

/// The end of the text and of the closing `"""` of the triple-quoted string at `start`.
pub fn triple_quoted_end<T: Copy + PartialEq + From<u8>>(
    text: &[T],
    start: usize,
) -> Result<(usize, usize), TripleQuoteError> {
    let quote: T = T::from(b'"');
    let mut index: usize = start + TRIPLE_QUOTE_LENGTH;
    while index < text.len() {
        if text[index] != quote {
            index += 1;
            continue;
        }
        let run: usize = text[index..]
            .iter()
            .take_while(|unit| **unit == quote)
            .count();
        if run >= TRIPLE_QUOTE_LENGTH {
            if run > LONGEST_CLOSING_RUN {
                return Err(TripleQuoteError::Inside(index));
            }
            return Ok((index + run - TRIPLE_QUOTE_LENGTH, index + run));
        }
        index += run;
    }
    Err(TripleQuoteError::Unclosed)
}
