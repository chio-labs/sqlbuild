use crate::header_metadata::models::{ThresholdBound, ThresholdInput};
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

/// One SCHEMA declaration `columns` value and its column names or first error.
pub(super) struct SchemaColumnsTestCase {
    pub(super) description: &'static str,
    pub(super) columns: Value,
    /// The comma-separated column names, or the first error message.
    pub(super) expected_summary: &'static str,
}

/// One threshold bound's operator and limits and the bound or error it produces.
pub(super) struct ThresholdBoundTestCase {
    pub(super) description: &'static str,
    pub(super) operator: &'static str,
    pub(super) inputs: (ThresholdInput, ThresholdInput, ThresholdInput),
    pub(super) expected_bound: Result<ThresholdBound, &'static str>,
}

/// One measurement contract's fields and the error it produces, if any.
pub(super) struct MeasurementContractTestCase {
    pub(super) description: &'static str,
    pub(super) fields: (&'static str, Option<&'static str>, Option<&'static str>),
    pub(super) expected_result: Result<(), &'static str>,
}
