pub(crate) struct SemanticValidationTestCase {
    pub(crate) description: &'static str,
    pub(crate) request: &'static str,
    pub(crate) expected_complete: bool,
}
