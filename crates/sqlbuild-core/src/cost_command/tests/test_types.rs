use crate::cost_command::models::CostCoverage;

pub(super) struct ValidationTestCase {
    pub(super) description: &'static str,
    pub(super) selector: &'static str,
    pub(super) limits: (Option<i64>, bool),
    pub(super) sort_field: &'static str,
    pub(super) has_bounds: bool,
    pub(super) expected_code: Option<&'static str>,
}

pub(super) struct SelectionTestCase {
    pub(super) description: &'static str,
    pub(super) selector: &'static str,
    pub(super) expected_index: Option<usize>,
    pub(super) expected_code: Option<&'static str>,
}

pub(super) struct RefreshTestCase {
    pub(super) description: &'static str,
    pub(super) current: CostCoverage,
    pub(super) candidate: CostCoverage,
    pub(super) expected_accepted: Option<bool>,
}

pub(super) struct ScalarTestCase {
    pub(super) description: &'static str,
    pub(super) value: &'static str,
    pub(super) limits: (Option<i64>, bool),
    pub(super) expected_zero: bool,
    pub(super) expected_limit: Option<i64>,
}
