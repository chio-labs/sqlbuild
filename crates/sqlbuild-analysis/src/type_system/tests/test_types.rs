use crate::type_system::_helpers::python_text::PythonInt;

pub(super) struct NormalizeTypeTestCase {
    pub(super) description: &'static str,
    pub(super) type_sql: &'static str,
    pub(super) dialect: &'static str,
    /// `name | family | precision | scale | length | parse error`, or None to defer.
    pub(super) expected_normalization: Option<&'static str>,
}

pub(super) struct PythonIntTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) expected_value: PythonInt,
}

pub(super) struct SplitTypeTestCase {
    pub(super) description: &'static str,
    pub(super) type_sql: &'static str,
    pub(super) expected_split: Option<(&'static str, Vec<i64>)>,
}

pub(super) struct BracketDepthTestCase {
    pub(super) description: &'static str,
    pub(super) depth: usize,
    pub(super) expected_native: bool,
}
