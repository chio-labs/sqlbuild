use crate::tests::test_types::Value;

/// One header's `columns` and `audits` values and the parse the native parser must produce.
pub(super) struct HeaderMetadataTestCase {
    pub(super) description: &'static str,
    pub(super) columns: Value,
    pub(super) audits: Value,
    /// Lines per column then model audit, or the first error message, or `unsupported`.
    pub(super) expected_summary: Result<&'static [&'static str], &'static str>,
}

/// One header `dynamic_columns` value and its families or first error.
pub(super) struct DynamicColumnsTestCase {
    pub(super) description: &'static str,
    pub(super) raw: Value,
    /// `name:aggregate:pattern` per family, or the first error message.
    pub(super) expected_families: Result<&'static [&'static str], &'static str>,
}

/// One header `audit_factories` value and its references or first error.
pub(super) struct FactoryReferencesTestCase {
    pub(super) description: &'static str,
    pub(super) raw: Value,
    pub(super) expected_references: Result<&'static [&'static str], &'static str>,
}
