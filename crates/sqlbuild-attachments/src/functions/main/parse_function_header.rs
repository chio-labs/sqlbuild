//! Python's SQL and Python function header parsing, before template expansion.

use crate::functions::_helpers::header_parsing::{HeaderErrors, parsed_header};
use crate::functions::models::{FunctionHeader, FunctionLanguage, HeaderValue};

/// The parsed header of the function file at `relative_path`, with Python's first error.
#[must_use]
pub fn parse_function_header(
    header: &[(String, HeaderValue)],
    language: FunctionLanguage,
    relative_path: &str,
) -> FunctionHeader {
    parsed_header(
        header,
        &HeaderErrors {
            language,
            relative_path,
        },
    )
}
