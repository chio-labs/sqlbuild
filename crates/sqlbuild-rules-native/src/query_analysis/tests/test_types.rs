use serde_json::Value;

pub(crate) struct QueryAnalysisExpectedValue {
    pub(crate) pointer: &'static str,
    pub(crate) value: &'static str,
}

pub(crate) struct QueryAnalysisTestCase {
    pub(crate) description: &'static str,
    pub(crate) request: Value,
    pub(crate) analyze: fn(&str) -> Result<String, String>,
    pub(crate) expected_length: usize,
    pub(crate) expected_values: Vec<QueryAnalysisExpectedValue>,
    pub(crate) expected_nonempty_strings: Vec<&'static str>,
}
