//! A header quote error located in its file, with the message and help it reports.

use crate::header_strings::constants::{
    DOUBLE_QUOTE_INSIDE, DOUBLE_QUOTE_INSIDE_HELP, DOUBLE_QUOTE_INSIDE_MESSAGE, POSITION_SUFFIX,
    SINGLE_QUOTE_INSIDE, SINGLE_QUOTE_INSIDE_HELP, SINGLE_QUOTE_INSIDE_MESSAGE,
    TRIPLE_QUOTE_INSIDE, TRIPLE_QUOTE_INSIDE_HELP, TRIPLE_QUOTE_INSIDE_MESSAGE,
    UNCLOSED_TRIPLE_QUOTE, UNCLOSED_TRIPLE_QUOTE_HELP, UNCLOSED_TRIPLE_QUOTE_MESSAGE,
};
use crate::header_strings::models::QuoteFailure;

const QUOTE_ERRORS: [(&str, &str, &str); 4] = [
    (
        DOUBLE_QUOTE_INSIDE,
        DOUBLE_QUOTE_INSIDE_MESSAGE,
        DOUBLE_QUOTE_INSIDE_HELP,
    ),
    (
        SINGLE_QUOTE_INSIDE,
        SINGLE_QUOTE_INSIDE_MESSAGE,
        SINGLE_QUOTE_INSIDE_HELP,
    ),
    (
        TRIPLE_QUOTE_INSIDE,
        TRIPLE_QUOTE_INSIDE_MESSAGE,
        TRIPLE_QUOTE_INSIDE_HELP,
    ),
    (
        UNCLOSED_TRIPLE_QUOTE,
        UNCLOSED_TRIPLE_QUOTE_MESSAGE,
        UNCLOSED_TRIPLE_QUOTE_HELP,
    ),
];

/// The located failure for header syntax `error` in `header`, if it is a quote error.
///
/// `header_start` is the one-based file line and column of the header text's first character.
pub fn quote_failure(
    error: &str,
    header: &str,
    header_start: (usize, usize),
) -> Option<QuoteFailure> {
    QUOTE_ERRORS.iter().find_map(|(kind, message, help)| {
        let digits: &str = error.strip_prefix(*kind)?.strip_prefix(POSITION_SUFFIX)?;
        let position: usize = digits.parse().ok()?;
        let (line, column) = location(header, position, header_start);
        Some(QuoteFailure {
            position,
            line,
            column,
            message: (*message).to_owned(),
            help: (*help).to_owned(),
        })
    })
}

/// The one-based file line and column of character offset `position` in `header`.
fn location(
    header: &str,
    position: usize,
    (header_line, header_column): (usize, usize),
) -> (usize, usize) {
    let mut line: usize = header_line;
    let mut column: usize = header_column;
    for character in header.chars().take(position) {
        if character == '\n' {
            line += 1;
            column = 1;
        } else {
            column += 1;
        }
    }
    (line, column)
}
