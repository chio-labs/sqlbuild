pub(super) struct NamePatternTestCase {
    pub(super) description: &'static str,
    pub(super) pattern: &'static str,
    pub(super) column_name: &'static str,
    pub(super) expected_match: Result<bool, &'static str>,
}
