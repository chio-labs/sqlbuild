pub(super) struct SqlTestModeTestCase {
    pub(super) description: &'static str,
    pub(super) sql_body: &'static str,
    pub(super) expected_mode: Result<&'static str, &'static str>,
}
