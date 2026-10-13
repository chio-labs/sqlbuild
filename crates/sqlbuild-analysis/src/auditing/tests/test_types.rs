use crate::auditing::models::{MeasurementOutcome, Thresholds};

pub(crate) struct GateIdentityTestCase {
    pub(crate) description: &'static str,
    pub(crate) measurement_name: &'static str,
    pub(crate) expected_binding_set_hash: &'static str,
    pub(crate) expected_blocking_set_hash: &'static str,
    pub(crate) expected_order: [usize; 2],
}

pub(crate) struct MeasurementTestCase {
    pub(crate) description: &'static str,
    pub(crate) measured: f64,
    pub(crate) samples: (Option<i128>, Option<i128>),
    pub(crate) thresholds: Thresholds,
    pub(crate) expected_outcome: Result<MeasurementOutcome, &'static str>,
}

pub(crate) struct ReplaceTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_sql: &'static str,
}
