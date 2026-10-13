pub(super) struct LiteralSqlTestCase {
    pub(super) description: &'static str,
    pub(super) source: &'static str,
    pub(super) expected_calls: &'static [(&'static str, &'static str, usize)],
}
