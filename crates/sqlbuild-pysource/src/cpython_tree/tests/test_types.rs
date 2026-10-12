pub(super) struct JoinedConstantTestCase {
    pub(super) description: &'static str,
    pub(super) source: &'static str,
    pub(super) expected_constants: &'static [(&'static str, usize, usize)],
}
