pub(crate) struct DiffSelectionTestCase {
    pub(crate) description: &'static str,
    pub(crate) select: &'static [&'static str],
    pub(crate) exclude: &'static [&'static str],
    /// The selected resources, sorted, or the error code.
    pub(crate) expected_selection: Result<&'static [usize], &'static str>,
}
