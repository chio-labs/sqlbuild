use crate::relationship_names::models::{ExpectedNames, TopLevelCtes};

/// One SQL test body and the native expected-model outcome.
pub(super) struct ExpectedNamesTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_outcome: ExpectedNames,
}

/// One scenario body and the native expected-model outcome.
pub(super) struct ScenarioNamesTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_outcome: ExpectedNames,
}

/// One SQL text and the CTEs Python's scanner reads, or its error.
pub(super) struct TopLevelCtesTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_outcome: TopLevelCtes,
}

/// One dialect's lexical rules as the Python adapter declares them.
pub(super) struct SyntaxTestCase {
    pub(super) description: &'static str,
    pub(super) backslash_escape_quotes: &'static [&'static str],
    pub(super) nested_block_comments: bool,
    pub(super) line_comment_prefixes: &'static [&'static str],
    pub(super) sql: &'static str,
    pub(super) expected_outcome: ExpectedNames,
}
