use crate::json::models::JsonValue;

pub(super) struct NormalizeTestCase {
    pub(super) description: &'static str,
    pub(super) record: JsonValue,
    pub(super) expected_error: Option<&'static str>,
    pub(super) expected_encoded: Option<&'static str>,
}
