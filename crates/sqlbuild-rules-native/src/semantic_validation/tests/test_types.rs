pub(crate) struct SemanticValidationTestCase {
    pub(crate) description: &'static str,
    pub(crate) request: &'static str,
    pub(crate) expected_complete: bool,
}

pub(crate) struct SemanticValidationBatchTestCase {
    pub(crate) description: &'static str,
    pub(crate) request: &'static str,
    pub(crate) expected_validity: [bool; 2],
}
