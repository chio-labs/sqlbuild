use crate::sql_scan::models::QuotePolicy;
use crate::sql_scan::models::Unclosed;

pub(crate) struct MatchingParenPolicyTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) policy: QuotePolicy,
    pub(crate) expected_close: Result<usize, Unclosed>,
}

pub(crate) struct NonCodeEndTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) policy: QuotePolicy,
    pub(crate) expected_end: Result<Option<usize>, Unclosed>,
}

pub(crate) struct DialectFirstNonCodeRangeTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) syntax: crate::sql_scan::models::LexicalSyntax,
    pub(crate) expected_first_range: Option<(usize, usize)>,
}

pub(crate) struct DialectNonCodeRangesTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) syntax: crate::sql_scan::models::LexicalSyntax,
    pub(crate) expected_marker_protected: bool,
}
