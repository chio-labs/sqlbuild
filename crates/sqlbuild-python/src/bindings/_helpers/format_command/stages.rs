//! The per-file native work of a format run: header lint and header formatting.

use sqlbuild_rules::dsl_headers::constants::RULE_HEADER_PARSE;
use sqlbuild_rules::dsl_headers::main::format_headers::format_headers;
use sqlbuild_rules::dsl_headers::main::scan_headers::scan_headers;
use sqlbuild_rules::dsl_headers::models::{HeaderRulesConfig, HeaderViolation};

use crate::bindings::_helpers::rules::dsl_headers::header_violations;
use crate::bindings::_helpers::rules::native_header_parser::NativeHeaderParser;

/// Every header rule violation of `text`.
pub(crate) fn lint_header_text(
    text: &str,
    config: HeaderRulesConfig,
) -> Result<Vec<HeaderViolation>, String> {
    let characters: Vec<char> = text.chars().collect();
    header_violations(&characters, &scan_headers(&characters, false), config)
}

/// The header-parse faults among `violations`.
pub(crate) fn parse_faults(violations: &[HeaderViolation]) -> Vec<HeaderViolation> {
    violations
        .iter()
        .filter(|violation| violation.code == RULE_HEADER_PARSE)
        .cloned()
        .collect()
}

/// `text` with header formatting fixes applied, and the faults relocation reported.
pub(crate) fn format_header_text(
    text: &str,
    config: HeaderRulesConfig,
) -> Result<(String, Vec<HeaderViolation>), String> {
    let characters: Vec<char> = text.chars().collect();
    let (formatted, faults) = format_headers(&characters, config, &NativeHeaderParser)?;
    Ok((formatted.into_iter().collect(), faults))
}

/// `operation` over every item, in item order; the first failure in item order is returned.
pub(crate) fn each_file<T: Sync, R: Send>(
    items: &[T],
    operation: impl Fn(&T) -> Result<R, String> + Sync,
) -> Result<Vec<R>, String> {
    items.iter().map(operation).collect()
}
