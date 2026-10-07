/// One SQL text and the expected-model names the native scan returns, or `None` for a deferral.
pub(super) struct ExpectedNamesTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_names: Option<&'static [&'static str]>,
}

/// One dialect's lexical rules as the Python adapter declares them.
pub(super) struct SyntaxTestCase {
    pub(super) description: &'static str,
    pub(super) backslash_escape_quotes: &'static [&'static str],
    pub(super) nested_block_comments: bool,
    pub(super) line_comment_prefixes: &'static [&'static str],
    pub(super) sql: &'static str,
    pub(super) expected_names: Option<&'static [&'static str]>,
}
