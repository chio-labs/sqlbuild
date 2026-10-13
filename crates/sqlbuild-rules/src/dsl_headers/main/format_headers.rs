//! `format_headers`: a file with every header formatting fix applied.

use crate::dsl_headers::_helpers::formatting::{
    relocate_leading_comment, without_trailing_whitespace, wrap_audits, wrap_descriptions,
};
use crate::dsl_headers::main::scan_headers::scan_headers;
use crate::dsl_headers::models::{HeaderRulesConfig, HeaderSpan, HeaderViolation};
use crate::dsl_headers::types::HeaderParser;

/// `text` with every header formatting fix applied, and the faults relocation reported.
pub fn format_headers<P: HeaderParser>(
    text: &[char],
    config: HeaderRulesConfig,
    parser: &P,
) -> Result<(Vec<char>, Vec<HeaderViolation>), P::Error> {
    let headers: Vec<HeaderSpan> = scan_headers(text, false);
    let trimmed: Vec<char> = without_trailing_whitespace(text, &headers);
    let (relocated, faults) = relocate_leading_comment(&trimmed, config, &headers, parser)?;
    let relocated_headers: Vec<HeaderSpan> = scan_headers(&relocated, false);
    let wrapped: Vec<char> =
        wrap_descriptions(&relocated, &relocated_headers, config.line_width, parser)?;
    Ok((wrap_audits(&wrapped, config.line_width, parser)?, faults))
}
