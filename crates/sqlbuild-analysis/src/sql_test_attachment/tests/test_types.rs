pub(crate) struct ScenarioExtractionTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_json: &'static str,
}

pub(crate) struct BatchClassificationTestCase {
    pub(crate) description: &'static str,
    pub(crate) request: &'static str,
    pub(crate) expected_response: &'static str,
}

pub(crate) struct ExtractionParityTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) mode: &'static str,
    pub(crate) expected_matches: bool,
}

pub(crate) struct ScenarioClassificationTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) file_label: &'static str,
    pub(crate) syntax: &'static str,
    pub(crate) expected_outcome: &'static str,
}

pub(crate) struct AssertionTargetsTestCase {
    pub(crate) description: &'static str,
    pub(crate) assertions: &'static [&'static str],
    pub(crate) syntax: &'static str,
    pub(crate) expected_targets: &'static [&'static str],
}

pub(crate) struct HelperReadsTestCase {
    pub(crate) description: &'static str,
    pub(crate) body: &'static str,
    pub(crate) expected_reads: Option<&'static [&'static str]>,
}

pub(crate) struct AuthoredOffsetTestCase {
    pub(crate) description: &'static str,
    pub(crate) contents: &'static str,
    pub(crate) authored: &'static str,
    pub(crate) span: Option<(usize, usize)>,
    pub(crate) body_offset: usize,
    pub(crate) marker: &'static str,
    pub(crate) expected_line_column: (usize, usize),
}

pub(crate) struct StoredScanTestCase {
    pub(crate) description: &'static str,
    pub(crate) value: String,
    pub(crate) modes: &'static [&'static str],
    pub(crate) expected_reused: bool,
}

/// `(name, body)` CTEs of one model test.
pub(crate) type CteRows = &'static [(&'static str, &'static str)];

pub(crate) struct AttachmentCheckTestCase {
    pub(crate) description: &'static str,
    pub(crate) authored: CteRows,
    pub(crate) expected: CteRows,
    pub(crate) assertions: CteRows,
    /// Mocked models and sources.
    pub(crate) mocks: (&'static [&'static str], &'static [&'static str]),
    /// Read helper names and reference target models.
    pub(crate) expected_reads: (&'static [&'static str], &'static [&'static str]),
    pub(crate) expected_problems: &'static [&'static str],
    pub(crate) expected_without_target: &'static str,
}

/// `[A-Za-z_][\\w$]*` matches for ASCII SQL, standing in for the host's Python `re`.
pub(crate) struct AsciiMatcher;

pub(super) struct TokensTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_tokens: &'static [&'static str],
}

pub(super) struct ReadsWordTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) word: &'static str,
    pub(super) expected_reads: bool,
}

pub(super) struct CteLocationTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    pub(super) sql_body: &'static str,
    pub(super) cte_name: &'static str,
    pub(super) call: Option<&'static str>,
    /// Line, column, end line and end column.
    pub(super) expected_location: (usize, usize, usize, usize),
}
