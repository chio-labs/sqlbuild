//! A prose string of a header: its delimiters checked and its text folded.

use crate::header_strings::constants::TRIPLE_QUOTE_LENGTH;
use crate::header_strings::main::fold_prose::fold_prose;
use crate::header_strings::main::opens_triple_quote::opens_triple_quote;
use crate::header_strings::main::prose_end::prose_end;
use crate::header_strings::main::prose_error_message::prose_error_message;
use crate::header_strings::main::triple_quoted_end::triple_quoted_end;
use crate::header_strings::models::{HeaderQuote, ProseString};

/// The text of a `'...'` string's inside: `\x` is `x`, and `''` is `'`.
fn unescaped_single(inside: &[char]) -> String {
    let mut text: String = String::with_capacity(inside.len());
    let mut index: usize = 0;
    while index < inside.len() {
        let escape: bool = inside[index] == '\\'
            || (inside[index] == '\'' && inside.get(index + 1) == Some(&'\''));
        if escape && index + 1 < inside.len() {
            index += 1;
        }
        text.push(inside[index]);
        index += 1;
    }
    text
}

/// The prose string that opens at character offset `start` of `text`, or its header syntax error.
pub fn prose_string(text: &[char], start: usize) -> Result<ProseString, String> {
    let end: usize =
        prose_end(text, start).map_err(|error| prose_error_message(error, text[start]))?;
    let (quote, written): (HeaderQuote, String) = if opens_triple_quote(text, start) {
        let content_end: usize = triple_quoted_end(text, start)
            .map_or(end - TRIPLE_QUOTE_LENGTH, |(content_end, _)| content_end);
        (
            HeaderQuote::Triple,
            text[start + TRIPLE_QUOTE_LENGTH..content_end]
                .iter()
                .collect(),
        )
    } else if text[start] == '"' {
        (
            HeaderQuote::Double,
            text[start + 1..end - 1].iter().collect(),
        )
    } else {
        (
            HeaderQuote::Single,
            unescaped_single(&text[start + 1..end - 1]),
        )
    };
    Ok(ProseString {
        quote,
        start,
        end,
        value: fold_prose(&written),
    })
}
