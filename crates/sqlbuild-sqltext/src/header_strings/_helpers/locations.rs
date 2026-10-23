//! Header quote errors: which they are, and where in the file they point.

use crate::header_strings::constants::{
    DOUBLE_QUOTE_INSIDE, DOUBLE_QUOTE_INSIDE_HELP, DOUBLE_QUOTE_INSIDE_MESSAGE, POSITION_SUFFIX,
    SINGLE_QUOTE_INSIDE, SINGLE_QUOTE_INSIDE_HELP, SINGLE_QUOTE_INSIDE_MESSAGE,
    TRIPLE_QUOTE_INSIDE, TRIPLE_QUOTE_INSIDE_HELP, TRIPLE_QUOTE_INSIDE_MESSAGE,
    UNCLOSED_TRIPLE_QUOTE, UNCLOSED_TRIPLE_QUOTE_HELP, UNCLOSED_TRIPLE_QUOTE_MESSAGE,
};

/// Each quote error's kind, then the message and help it reports.
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

/// The header position, message and help of quote error `error`, if it is one.
pub(crate) fn quote_error(error: &str) -> Option<(usize, &'static str, &'static str)> {
    QUOTE_ERRORS.iter().find_map(|(kind, message, help)| {
        let digits: &str = error.strip_prefix(*kind)?.strip_prefix(POSITION_SUFFIX)?;
        let Ok(position) = digits.parse::<usize>() else {
            return None;
        };
        Some((position, *message, *help))
    })
}

/// The one-based file line and column of character offset `position` in `header`.
pub(crate) fn location(
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
