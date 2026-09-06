pub(crate) struct LintTestCase {
    pub description: &'static str,
    pub sql: &'static str,
    pub expected_codes: &'static [&'static str],
    pub expected_anchors: &'static [(&'static str, &'static str)],
}

pub(crate) struct FormatTestCase {
    pub description: &'static str,
    pub sql: &'static str,
    pub expected_sql: &'static str,
    pub expected_changed: bool,
}

pub(crate) struct InvalidRuleTestCase {
    pub description: &'static str,
    pub rule: &'static str,
    pub expected_message: &'static str,
}
