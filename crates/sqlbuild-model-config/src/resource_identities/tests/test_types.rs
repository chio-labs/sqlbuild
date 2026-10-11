pub(super) struct ResourceIdentityTestCase {
    pub(super) description: &'static str,
    pub(super) name: &'static str,
    pub(super) private_identity: bool,
    pub(super) expected_suggestion: Option<&'static str>,
}
