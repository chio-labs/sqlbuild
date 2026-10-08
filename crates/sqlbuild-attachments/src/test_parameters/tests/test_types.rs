pub(super) struct ParameterReferenceTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    /// `(start, end, name)` by code points, up to Python's first error.
    pub(super) expected_references: Vec<(usize, usize, &'static str)>,
    pub(super) expected_error: Option<&'static str>,
}
