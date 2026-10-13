use sqlbuild_core::json::models::JsonValue;

pub(crate) struct StoreKeyTestCase {
    pub(crate) description: &'static str,
    pub(crate) value: JsonValue,
    pub(crate) expected_key: Option<&'static str>,
}
