use crate::model_validation::models::{Rejected, RetentionOverride, TableTypeOverride};
use crate::tests::test_types::Value;

/// One effective config, its references, and whether native validation accepts it.
pub(super) struct AcceptTestCase {
    pub(super) description: &'static str,
    pub(super) config: Vec<(&'static str, Value)>,
    /// `kind:name` per reference.
    pub(super) references: &'static [&'static str],
    pub(super) query_sql: &'static str,
    pub(super) expected_accepted: bool,
}

/// One header `time_travel_retention` value and the override Python resolves.
pub(super) struct RetentionOverrideTestCase {
    pub(super) description: &'static str,
    pub(super) value: Option<Value>,
    pub(super) expected_override: Result<RetentionOverride, Rejected>,
}

/// One header `table_type` value and the override Python resolves.
pub(super) struct TableTypeOverrideTestCase {
    pub(super) description: &'static str,
    pub(super) value: Option<Value>,
    pub(super) expected_override: Result<TableTypeOverride, Rejected>,
}
