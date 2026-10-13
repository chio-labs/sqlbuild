use crate::lint_text::models::{Neutralized, RetainedViolation};

pub(crate) struct NeutralizeTestCase {
    pub(crate) description: &'static str,
    pub(crate) body: &'static str,
    pub(crate) formatting: bool,
    pub(crate) expected_text: &'static str,
    pub(crate) expected_sites: Vec<(&'static str, usize, usize)>,
}

pub(crate) struct ParameterTestCase {
    pub(crate) description: &'static str,
    pub(crate) body: &'static str,
    pub(crate) neutralize: fn(&str) -> Neutralized,
    pub(crate) expected_text: &'static str,
}

pub(crate) struct RestoreTestCase {
    pub(crate) description: &'static str,
    pub(crate) body: &'static str,
    pub(crate) fixed: &'static str,
    pub(crate) expected_restored: Result<String, String>,
}

pub(crate) struct TokenAtTestCase {
    pub(crate) description: &'static str,
    pub(crate) body: &'static str,
    pub(crate) start: usize,
    pub(crate) expected_token: Option<&'static str>,
}

pub(crate) struct SuppressionTestCase {
    pub(crate) description: &'static str,
    pub(crate) contents: &'static str,
    pub(crate) violations: Vec<(usize, &'static str)>,
    pub(crate) allow: bool,
    pub(crate) expected_retained: Vec<RetainedViolation>,
}
