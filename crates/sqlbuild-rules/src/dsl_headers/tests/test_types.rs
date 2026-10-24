use std::convert::Infallible;

use sqlbuild_sqltext::compiler::main::model_header_single_parsing::parse_one;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

use crate::dsl_headers::models::{ParseFailure, ParseOutcome};
use crate::dsl_headers::types::HeaderParser;

/// Parses a header with the compiler's header parser.
pub(crate) struct NativeParser;

impl HeaderParser for NativeParser {
    type Values = AuthoredValue;
    type Error = Infallible;

    fn parse(&self, _kind: &str, inner: &str) -> ParseOutcome<AuthoredValue, Infallible> {
        match parse_one(inner) {
            (Some(value), _, None) => ParseOutcome::Parsed(value),
            (_, _, error) => ParseOutcome::Rejected(ParseFailure {
                message: error.unwrap_or_default(),
                help: None,
                position: None,
            }),
        }
    }

    fn description(&self, values: &AuthoredValue) -> Result<Option<String>, Infallible> {
        Ok(match values {
            AuthoredValue::Map(entries) => entries.iter().find_map(|(key, value)| match value {
                AuthoredValue::String(text) if key == "description" => Some(text.clone()),
                _ => None,
            }),
            _ => None,
        })
    }

    fn same(&self, left: &AuthoredValue, right: &AuthoredValue) -> Result<bool, Infallible> {
        Ok(left == right)
    }
}

/// Parses a header to its text without whitespace or trailing commas.
pub(crate) struct CompactParser;

impl HeaderParser for CompactParser {
    type Values = String;
    type Error = Infallible;

    fn parse(&self, _kind: &str, inner: &str) -> ParseOutcome<String, Infallible> {
        let compact: String = inner
            .chars()
            .filter(|character| !character.is_whitespace())
            .collect();
        ParseOutcome::Parsed(compact.replace(",]", "]").replace(",)", ")"))
    }

    fn description(&self, values: &String) -> Result<Option<String>, Infallible> {
        Ok(values.contains("description").then(|| values.clone()))
    }

    fn same(&self, left: &String, right: &String) -> Result<bool, Infallible> {
        Ok(left == right)
    }
}

pub(crate) struct ScanTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) expected_spans: Vec<(&'static str, usize, usize)>,
    pub(crate) expected_bodies: Vec<(usize, usize)>,
    pub(crate) expected_measurements: Vec<(usize, usize)>,
}

pub(crate) struct FormatTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) line_width: i64,
    pub(crate) expected_text: &'static str,
}

pub(crate) struct ProseTestCase {
    pub(crate) description: &'static str,
    pub(crate) prose: &'static str,
    pub(crate) expected_wrapped: &'static str,
}

pub(crate) struct QuoteFixTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) expected_text: &'static str,
    pub(crate) expected_lines: Vec<usize>,
}

pub(crate) struct LengthTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: String,
    pub(crate) expected_too_long: bool,
}
