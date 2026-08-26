use serde_json::Value;

pub(crate) struct NativeEvaluationTestCase {
    pub(crate) description: &'static str,
    pub(crate) config: Value,
    pub(crate) expected_faults: Value,
}

pub(crate) struct ThresholdEvaluationTestCase {
    pub(crate) description: &'static str,
    pub(crate) config: Value,
    pub(crate) query_sql: &'static str,
    pub(crate) references: Value,
    pub(crate) expected_codes: &'static [&'static str],
}

pub(crate) struct ThresholdFingerprintTestCase {
    pub(crate) description: &'static str,
    pub(crate) base_config: Value,
    pub(crate) overridden_config: Value,
    pub(crate) expected_different: bool,
}

pub(crate) struct ScopeFactsTestCase {
    pub(crate) description: &'static str,
    pub(crate) scope: Value,
    pub(crate) expected_complete: bool,
    pub(crate) expected_runtime_usage: bool,
    pub(crate) expected_declaration_count: usize,
    pub(crate) expected_visibility_count: usize,
}

pub(crate) struct MalformedScopeFactsTestCase {
    pub(crate) description: &'static str,
    pub(crate) scope: Value,
    pub(crate) expected_rejected: bool,
}

pub(crate) struct MissingScopeFactsTestCase {
    pub(crate) description: &'static str,
    pub(crate) expected_complete: bool,
    pub(crate) expected_runtime_usage: bool,
}
