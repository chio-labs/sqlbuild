pub(super) struct StringLocationTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    pub(super) names: &'static [&'static str],
    pub(super) context: Option<&'static str>,
    pub(super) expected_locations: &'static [(usize, usize)],
}
