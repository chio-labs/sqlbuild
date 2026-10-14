use crate::rule_results::models::RuleFinding;

pub(crate) struct HintTestCase {
    pub(crate) description: &'static str,
    pub(crate) paths: Vec<&'static str>,
    pub(crate) expected_hint: Option<&'static str>,
}

pub(crate) struct ResultTestCase {
    pub(crate) description: &'static str,
    pub(crate) json_output: bool,
    pub(crate) expected_text: &'static str,
}

pub(crate) struct ProgressTestCase {
    pub(crate) description: &'static str,
    pub(crate) elapsed_seconds: f64,
    pub(crate) timings_ms: (i64, i64),
    pub(crate) skipped_rules: Option<Vec<String>>,
    pub(crate) expected_message: &'static str,
}

pub(crate) struct GroupTestCase {
    pub(crate) description: &'static str,
    pub(crate) findings: Vec<RuleFinding>,
    pub(crate) expected_codes: Vec<&'static str>,
    pub(crate) expected_messages: Vec<&'static str>,
}
