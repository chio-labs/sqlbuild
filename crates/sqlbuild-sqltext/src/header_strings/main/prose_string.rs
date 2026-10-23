//! A prose string of a header: its delimiters checked and its text folded.

use crate::header_strings::constants::{
    DOUBLE_QUOTE_INSIDE, POSITION_SUFFIX, SINGLE_QUOTE_INSIDE, TRIPLE_QUOTE_INSIDE,
    TRIPLE_QUOTE_LENGTH, UNCLOSED_TRIPLE_QUOTE,
};
use crate::header_strings::errors::TripleQuoteError;
use crate::header_strings::main::fold_prose::fold_prose;
use crate::header_strings::main::opens_triple_quote::opens_triple_quote;
use crate::header_strings::main::triple_quoted_end::triple_quoted_end;
use crate::header_strings::models::{HeaderQuote, ProseString};

/// The header syntax error for `kind` at character offset `position`.
fn located(kind: &str, position: usize) -> String {
    format!("{kind}{POSITION_SUFFIX}{position}")
}

/// The prose string that opens at character offset `start` of `text`, or its header syntax error.
pub fn prose_string(text: &[char], start: usize) -> Result<ProseString, String> {
    if opens_triple_quote(text, start) {
        let (content_end, end) = triple_quoted_end(text, start).map_err(|error| match error {
            TripleQuoteError::Unclosed => located(UNCLOSED_TRIPLE_QUOTE, start),
            TripleQuoteError::Inside(position) => located(TRIPLE_QUOTE_INSIDE, position),
        })?;
        let written: String = text[start + TRIPLE_QUOTE_LENGTH..content_end]
            .iter()
            .collect();
        return Ok(ProseString {
            quote: HeaderQuote::Triple,
            start,
            end,
            value: fold_prose(&written),
        });
    }
    let quote: char = text[start];
    let (kind, inside) = if quote == '"' {
        (HeaderQuote::Double, DOUBLE_QUOTE_INSIDE)
    } else {
        (HeaderQuote::Single, SINGLE_QUOTE_INSIDE)
    };
    let mut index: usize = start + 1;
    while index < text.len() {
        if text[index] == '\\' {
            if text.get(index + 1) == Some(&quote) {
                return Err(located(inside, index + 1));
            }
            index += 2;
            continue;
        }
        if text[index] == quote {
            let written: String = text[start + 1..index].iter().collect();
            return Ok(ProseString {
                quote: kind,
                start,
                end: index + 1,
                value: fold_prose(&written),
            });
        }
        index += 1;
    }
    Err(format!(
        "unterminated {} string{POSITION_SUFFIX}{start}",
        if quote == '"' {
            "double-quoted"
        } else {
            "single-quoted"
        }
    ))
}
