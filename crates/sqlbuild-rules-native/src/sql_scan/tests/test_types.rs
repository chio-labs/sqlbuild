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
