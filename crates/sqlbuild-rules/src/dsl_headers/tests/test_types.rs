use std::convert::Infallible;

use crate::dsl_headers::models::ParseOutcome;
use crate::dsl_headers::types::HeaderParser;

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
    pub(crate) escaped: &'static str,
    pub(crate) expected_wrapped: &'static str,
    pub(crate) expected_decoded: &'static str,
}
