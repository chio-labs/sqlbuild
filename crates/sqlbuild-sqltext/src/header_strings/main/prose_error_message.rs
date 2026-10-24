//! The header syntax error a misquoted prose string reports.

use crate::header_strings::constants::{
    DOUBLE_QUOTE_INSIDE, POSITION_SUFFIX, SINGLE_QUOTE_INSIDE, TRIPLE_QUOTE_INSIDE,
    UNCLOSED_TRIPLE_QUOTE,
};
use crate::header_strings::errors::ProseError;

/// The header syntax error `error` reports, located by character offset.
pub fn prose_error_message(error: ProseError, quote: char) -> String {
    match error {
        ProseError::Unterminated(start) => format!(
            "unterminated {}-quoted string{POSITION_SUFFIX}{start}",
            if quote == '"' { "double" } else { "single" }
        ),
        ProseError::DoubleQuoteInside(position) => {
            format!("{DOUBLE_QUOTE_INSIDE}{POSITION_SUFFIX}{position}")
        }
        ProseError::SingleQuoteInside(position) => {
            format!("{SINGLE_QUOTE_INSIDE}{POSITION_SUFFIX}{position}")
        }
        ProseError::TripleQuoteInside(position) => {
            format!("{TRIPLE_QUOTE_INSIDE}{POSITION_SUFFIX}{position}")
        }
        ProseError::UnclosedTripleQuote(start) => {
            format!("{UNCLOSED_TRIPLE_QUOTE}{POSITION_SUFFIX}{start}")
        }
    }
}
