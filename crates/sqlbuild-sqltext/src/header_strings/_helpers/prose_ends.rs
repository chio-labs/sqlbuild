//! Where each kind of prose header string ends, by the quoting rules of prose.

use crate::header_strings::_helpers::separators::{run_on_after_close, separator_follows};
use crate::header_strings::errors::{ProseError, TripleQuoteError};
use crate::header_strings::main::closes_inside_text::closes_inside_text;
use crate::header_strings::main::triple_quoted_end::triple_quoted_end;

/// The end of the `"""..."""` string at `start`, checked not to close inside its text.
pub(crate) fn triple_end<T: Copy + PartialEq + From<u8> + Into<u32>>(
    text: &[T],
    start: usize,
) -> Result<usize, ProseError> {
    let (content_end, end) = triple_quoted_end(text, start).map_err(|error| match error {
        TripleQuoteError::Unclosed => ProseError::UnclosedTripleQuote(start),
        TripleQuoteError::Inside(position) => ProseError::TripleQuoteInside(position),
    })?;
    if closes_inside_text(text, end) {
        return Err(ProseError::TripleQuoteInside(content_end));
    }
    Ok(end)
}

/// The end of the `"..."` string at `start`, where a backslash is an ordinary character.
pub(crate) fn double_end<T: Copy + PartialEq + From<u8> + Into<u32>>(
    text: &[T],
    start: usize,
) -> Result<usize, ProseError> {
    let quote: T = T::from(b'"');
    let close: usize = (start + 1..text.len())
        .find(|index| text[*index] == quote)
        .ok_or(ProseError::Unterminated(start))?;
    let escaped: bool = close > start + 1 && text[close - 1] == T::from(b'\\');
    if run_on_after_close(text, close + 1) || (escaped && !separator_follows(text, close + 1)) {
        return Err(ProseError::DoubleQuoteInside(close));
    }
    Ok(close + 1)
}

/// The end of the `'...'` string at `start`, where `\\'` and `''` are quotes in the text.
pub(crate) fn single_end<T: Copy + PartialEq + From<u8> + Into<u32>>(
    text: &[T],
    start: usize,
) -> Result<usize, ProseError> {
    let quote: T = T::from(b'\'');
    let mut index: usize = start + 1;
    while index < text.len() {
        if text[index] == T::from(b'\\') {
            index += 2;
            continue;
        }
        if text[index] == quote {
            if text.get(index + 1) == Some(&quote) {
                index += 2;
                continue;
            }
            if run_on_after_close(text, index + 1) {
                return Err(ProseError::SingleQuoteInside(index));
            }
            return Ok(index + 1);
        }
        index += 1;
    }
    Err(ProseError::Unterminated(start))
}
