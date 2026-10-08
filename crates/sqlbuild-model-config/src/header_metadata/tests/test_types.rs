use crate::tests::test_types::Value;

/// One header's `columns` and `audits` values and the parse the native parser must produce.
pub(super) struct HeaderMetadataTestCase {
    pub(super) description: &'static str,
    pub(super) columns: Value,
    pub(super) audits: Value,
    /// Lines per column then model audit, or the first error message, or `unsupported`.
    pub(super) expected_summary: Result<&'static [&'static str], &'static str>,
}
