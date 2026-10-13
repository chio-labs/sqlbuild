pub(super) struct MarkerTestCase {
    pub(super) description: &'static str,
    pub(super) content: &'static str,
    pub(super) expected_content: &'static str,
}

pub(super) struct SummaryTestCase {
    pub(super) description: &'static str,
    pub(super) template: &'static str,
    pub(super) expected_text: &'static str,
}
