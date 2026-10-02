pub(crate) struct QualityRuleTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) rule: &'static str,
    pub(crate) relation_keys: &'static str,
    pub(crate) expected_anchors: &'static [&'static str],
    pub(crate) expected_fixed_sql: Option<&'static str>,
}

pub(crate) struct QualityScaleTestCase {
    pub(crate) description: &'static str,
    pub(crate) cte_count: usize,
    pub(crate) column_count: usize,
    pub(crate) expected_findings: usize,
    pub(crate) expected_max_seconds: f64,
}

pub(crate) struct QualityRemediationTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) rule: &'static str,
    pub(crate) expected_fragments: &'static [&'static str],
}
