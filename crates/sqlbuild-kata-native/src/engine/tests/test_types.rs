use serde_json::Value;

pub(crate) struct NativeEvaluationTestCase {
    pub(crate) description: &'static str,
    pub(crate) config: Value,
    pub(crate) expected_faults: Value,
}

pub(crate) struct DomainLayoutTestCase {
    pub(crate) description: &'static str,
    pub(crate) code: &'static str,
    pub(crate) models: Value,
    pub(crate) thresholds: Value,
    pub(crate) layout: Value,
    pub(crate) scope_index: Value,
    pub(crate) expected_codes: &'static [&'static str],
    pub(crate) expected_message_fragments: &'static [&'static str],
    pub(crate) expected_absent_fragments: &'static [&'static str],
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

pub(crate) struct SqlTestPolicyTestCase {
    pub(crate) description: &'static str,
    pub(crate) code: &'static str,
    pub(crate) tests: Value,
    pub(crate) scenarios: Value,
    pub(crate) scope_index: Value,
    pub(crate) config: Value,
    pub(crate) expected_fault_count: usize,
    pub(crate) expected_evaluated_models: usize,
    pub(crate) expected_paths: &'static [&'static str],
}

pub(crate) struct SqlTestPolicyCacheTestCase {
    pub(crate) description: &'static str,
    pub(crate) expected_first_misses: u64,
    pub(crate) expected_second_hits: u64,
    pub(crate) expected_second_misses: u64,
}
