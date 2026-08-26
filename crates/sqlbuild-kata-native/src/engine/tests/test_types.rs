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
