use crate::sql_scan::models::{LexicalSyntax, Unclosed};

pub(super) struct NonCodeEndTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) syntax: Option<LexicalSyntax>,
    pub(super) index: usize,
    pub(super) expected_end: Result<Option<usize>, Unclosed>,
}

pub(super) struct MatchingParenTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) open: usize,
    pub(super) expected_close: Result<usize, Unclosed>,
}
