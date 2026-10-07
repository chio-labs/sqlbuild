use crate::header_metadata::models::HeaderMetadataDeferral;
use crate::tests::test_types::Value;

/// One header's `columns` and `audits` values and the parse the native parser must produce.
pub(super) struct HeaderMetadataTestCase {
    pub(super) description: &'static str,
    pub(super) columns: Value,
    pub(super) audits: Value,
    /// `name type nullable audit,audit` per column, then `audit:argument,...` per model audit.
    pub(super) expected_summary: Result<&'static [&'static str], HeaderMetadataDeferral>,
}
