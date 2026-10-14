//! Fixture alignment regression inputs.

#[derive(Debug)]
pub(crate) struct AlignmentTestCase {
    pub(crate) description: &'static str,
    pub(crate) supplied: &'static [&'static str],
    pub(crate) required: &'static [&'static str],
    pub(crate) star: bool,
    pub(crate) typed_nulls: bool,
    pub(crate) expected_completed: Option<Vec<usize>>,
    pub(crate) expected_diagnostics: &'static [&'static str],
}
