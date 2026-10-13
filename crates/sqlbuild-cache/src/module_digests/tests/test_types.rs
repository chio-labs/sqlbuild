use sqlbuild_core::json::models::JsonValue;

pub(crate) struct MetadataTestCase {
    pub(crate) description: &'static str,
    pub(crate) rows: Vec<(JsonValue, JsonValue)>,
    pub(crate) expected_metadata: &'static str,
}
