//! A header quote error located in its file, with the message and help it reports.

use crate::header_strings::_helpers::locations::{location, quote_error};
use crate::header_strings::models::QuoteFailure;

/// The failure for quote error `error` in `header`, whose text starts at file `header_start`.
pub fn quote_failure(
    error: &str,
    header: &str,
    header_start: (usize, usize),
) -> Option<QuoteFailure> {
    let (position, message, help) = quote_error(error)?;
    let (line, column) = location(header, position, header_start);
    Some(QuoteFailure {
        position,
        line,
        column,
        message: message.to_owned(),
        help: help.to_owned(),
    })
}
