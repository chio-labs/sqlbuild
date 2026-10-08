use crate::model_validation::models::{RetentionOverride, TableTypeOverride, ValidationStop};
use crate::tests::test_types::Value;

/// One effective config, its references, and the outcome native validation reaches.
pub(super) struct ValidateTestCase {
    pub(super) description: &'static str,
    pub(super) config: Vec<(&'static str, Value)>,
    /// `kind:name` per reference.
    pub(super) references: &'static [&'static str],
    pub(super) query_sql: &'static str,
    /// `accepted`, `deferred`, or the exact error message.
    pub(super) expected_outcome: &'static str,
}

/// One header `time_travel_retention` value and the override Python resolves.
pub(super) struct RetentionOverrideTestCase {
    pub(super) description: &'static str,
    pub(super) value: Option<Value>,
    pub(super) expected_override: Result<RetentionOverride, ValidationStop>,
}

/// One header `table_type` value and the override Python resolves.
pub(super) struct TableTypeOverrideTestCase {
    pub(super) description: &'static str,
    pub(super) value: Option<Value>,
    pub(super) expected_override: Result<TableTypeOverride, ValidationStop>,
}
