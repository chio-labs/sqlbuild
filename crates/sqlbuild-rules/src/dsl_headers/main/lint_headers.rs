//! `lint_headers`: every header rule violation of a file's headers.

use crate::dsl_headers::_helpers::rules::{value_violations, whitespace_violation};
use crate::dsl_headers::_helpers::text::line_starts;
use crate::dsl_headers::models::{HeaderRulesConfig, HeaderSpan, HeaderViolation};
use crate::dsl_headers::types::HeaderParser;

/// Every header rule violation of `headers` in `text`, header by header.
pub fn lint_headers<P: HeaderParser>(
    text: &[char],
    headers: &[HeaderSpan],
    config: HeaderRulesConfig,
    parser: &P,
) -> Result<Vec<HeaderViolation>, P::Error> {
    let starts: Vec<usize> = line_starts(text);
    let mut violations: Vec<HeaderViolation> = Vec::new();
    for header in headers {
        violations.extend(value_violations((text, &starts), header, config, parser)?);
        violations.extend(whitespace_violation((text, &starts), header));
    }
    Ok(violations)
}
