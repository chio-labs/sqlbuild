use crate::compiler::_helpers::model_headers::tokenization;
use crate::compiler::models::NestingFailure;

/// The nesting failure `error` reports for `header`, starting on one-based `header_line`, if any.
pub fn header_nesting_failure(
    error: &str,
    header: &str,
    header_line: usize,
) -> Option<NestingFailure> {
    tokenization::nesting_failure(error, header, header_line)
}
