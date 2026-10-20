pub(super) struct EnumValueTestCase {
    pub(super) description: &'static str,
    pub(super) values: Vec<&'static str>,
    pub(super) parsed: Vec<Option<&'static str>>,
    pub(super) expected_values: Vec<&'static str>,
}
