use sqlbuild_sqltext::compiler::main::model_header_single_parsing::parse_one;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

use crate::dsl_headers::main::inner_header_text::inner_header_text;
use crate::dsl_headers::main::lint_headers::lint_headers;
use crate::dsl_headers::main::scan_headers::scan_headers;
use crate::dsl_headers::models::HeaderRulesConfig;
use crate::dsl_headers::tests::test_types::NativeParser;

pub(crate) fn chars(text: &str) -> Vec<char> {
    text.chars().collect()
}

/// The description each header of `text` stores, in order.
pub(crate) fn stored_descriptions(text: &[char]) -> Vec<Option<String>> {
    scan_headers(text, false)
        .iter()
        .map(|header| {
            let inner: String = inner_header_text(&text[header.start..header.end])
                .iter()
                .collect();
            let (Some(AuthoredValue::Map(entries)), _, None) = parse_one(&inner) else {
                return None;
            };
            entries
                .iter()
                .find(|(key, _)| key == "description")
                .and_then(|(_, value)| description_text(value))
        })
        .collect()
}

/// The text of a `description` value, if it is a string.
fn description_text(value: &AuthoredValue) -> Option<String> {
    let AuthoredValue::String(text) = value else {
        return None;
    };
    Some(text.clone())
}

/// The codes of the header violations of `text` at `(line_width, max_description_lines)`.
pub(crate) fn lint_codes(
    text: &str,
    (line_width, max_description_lines): (i64, usize),
) -> Vec<&'static str> {
    let characters: Vec<char> = chars(text);
    let config = HeaderRulesConfig {
        line_width,
        max_description_lines,
    };
    let Ok(violations) = lint_headers(
        &characters,
        &scan_headers(&characters, false),
        config,
        &NativeParser,
    );
    violations.iter().map(|violation| violation.code).collect()
}
