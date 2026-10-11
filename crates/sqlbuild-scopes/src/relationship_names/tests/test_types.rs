use crate::relationship_names::models::{ExpectedNames, RelationshipSource, TopLevelCtes};

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

/// A test file's relative path, `(name, sql, mode)` blocks and stored names.
pub(super) type FileCase = (
    &'static str,
    &'static [(&'static str, &'static str, &'static str)],
    Option<&'static [&'static [&'static str]]>,
);

/// Test files and scenarios, and the facts and faults their relationship scan reads.
pub(super) struct RelationshipFactsTestCase {
    pub(super) description: &'static str,
    /// `(relative path, [(name, sql, mode)], stored names)` per test file.
    pub(super) files: &'static [FileCase],
    /// `(name, relative path, sql)` per scenario.
    pub(super) scenarios: &'static [(&'static str, &'static str, &'static str)],
    /// `kind:name expected=.. called=.. tested=..` per fact.
    pub(super) expected_facts: &'static [&'static str],
    pub(super) expected_faults: &'static [(&'static str, &'static str)],
    /// Positions of the files whose scanned names would be stored.
    pub(super) expected_stored: &'static [usize],
}

/// Stored scan bytes and whether they decode as a file of `block_count` blocks.
pub(super) struct StoredNamesTestCase {
    pub(super) description: &'static str,
    pub(super) value: &'static str,
    pub(super) block_count: usize,
    pub(super) expected_names: Option<&'static [&'static [&'static str]]>,
}

/// A malformed test or scenario and the message its expected-model scan raises.
pub(super) struct ScanMessageTestCase {
    pub(super) description: &'static str,
    pub(super) source: RelationshipSource,
    pub(super) file_label: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_message: &'static str,
}
