pub(super) struct StatementFileTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    /// Each parsed block's header keys and SQL body, then the failure message if one stopped it.
    pub(super) expected_blocks: &'static [(&'static [&'static str], &'static str)],
    pub(super) expected_failure: Option<&'static str>,
}

/// A TEST header, and the same header as a SCENARIO, whose `cases` value nests `depth` maps deep.
pub(super) struct DeepStatementHeaderTestCase {
    pub(super) description: &'static str,
    pub(super) depth: usize,
    /// The test file's failure, then the scenario file's: each message and help.
    pub(super) expected_failures: [Option<(String, Option<String>)>; 2],
}

/// Scenario contents and the code-point span of the SQL after its header.
pub(super) struct ScenarioSpanTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    pub(super) expected_body_span: Option<(usize, usize)>,
}
