use crate::json::errors::JsonEmitError;
use crate::json::models::{JsonDialect, JsonValue};

pub(super) struct DumpsTestCase {
    pub(super) description: &'static str,
    pub(super) value: JsonValue,
    pub(super) dialect: JsonDialect,
    pub(super) expected_text: Result<&'static str, JsonEmitError>,
}

pub(super) struct FloatReprTestCase {
    pub(super) description: &'static str,
    pub(super) value: f64,
    pub(super) expected_repr: &'static str,
}

pub(super) struct IntegerParseTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) expected_decimal: Option<&'static str>,
}
