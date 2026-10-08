pub(super) struct ParameterReferenceTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    /// `(start, end, name)` by code points, or None where Python raises.
    pub(super) expected_references: Option<Vec<(usize, usize, &'static str)>>,
}
