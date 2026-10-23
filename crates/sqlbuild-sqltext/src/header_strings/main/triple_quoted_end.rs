//! Where a triple-quoted header string's text and closing delimiter end.

use crate::header_strings::constants::{LONGEST_CLOSING_RUN, TRIPLE_QUOTE_LENGTH};
use crate::header_strings::models::TripleQuoteError;
use crate::header_strings::types::HeaderChar;

/// The end of the text and the end of the closing `"""` of the string opening at `start`.
///
/// The first run of three or more double quotes closes the string. Up to two quotes before
/// the closing three belong to the text, so text may end with a quote; a longer run is a
/// `"""` inside the text.
pub fn triple_quoted_end<T: HeaderChar>(
    text: &[T],
    start: usize,
) -> Result<(usize, usize), TripleQuoteError> {
    let quote: T = T::ascii(b'"');
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
