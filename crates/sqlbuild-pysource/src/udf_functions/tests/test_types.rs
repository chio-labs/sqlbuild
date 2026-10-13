use crate::udf_functions::models::UdfShape;

pub(super) struct UdfFunctionTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    pub(super) expected_shape: Option<UdfShape>,
}
