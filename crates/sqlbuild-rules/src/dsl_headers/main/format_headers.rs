//! `format_headers`: a file with every header formatting fix applied.

use crate::dsl_headers::_helpers::formatting::{
    relocate_leading_comment, without_trailing_whitespace, wrap_audits, wrap_descriptions,
};
use crate::dsl_headers::_helpers::macro_header::changes_macro;
use crate::dsl_headers::_helpers::macro_header::layout_macro_headers;
use crate::dsl_headers::constants::{PROSE_LAYOUT_HEADER_KINDS, SQL_MACRO_HEADER_KIND};
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
    let relocated_headers: Vec<HeaderSpan> = if relocated.as_slice() == text {
        headers
    } else {
        scan_headers(&relocated, false)
    };
    let wrapped: Vec<char> = wrap_descriptions(
        &relocated,
        &relocated_headers,
        (&PROSE_LAYOUT_HEADER_KINDS, config.line_width),
        parser,
    )?;
    let audited: Vec<char> = wrap_audits(&wrapped, config.line_width, parser)?;
    let macro_headers: Vec<HeaderSpan> = scan_headers(&audited, false);
    let mut laid_out: Vec<char> = layout_macro_headers(&audited, &macro_headers, config.line_width);
    let defines_macro: bool = macro_headers
        .iter()
        .any(|header| header.kind == SQL_MACRO_HEADER_KIND);
    if defines_macro && changes_macro(&audited, &laid_out) {
        laid_out = audited;
    }
    let laid_out_headers: Vec<HeaderSpan> = scan_headers(&laid_out, false);
    Ok((
        wrap_descriptions(
            &laid_out,
            &laid_out_headers,
            (&[SQL_MACRO_HEADER_KIND], config.line_width),
            parser,
        )?,
        faults,
    ))
}
