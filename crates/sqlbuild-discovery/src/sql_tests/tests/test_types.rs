pub(super) struct StatementFileTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    /// Each parsed block's header keys and SQL body, then the failure message if one stopped it.
    pub(super) expected_blocks: &'static [(&'static [&'static str], &'static str)],
    pub(super) expected_failure: Option<&'static str>,
}
