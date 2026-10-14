use crate::algebra::models::{Grain, Scalar};

pub(super) struct HorizonTestCase {
    pub(super) description: &'static str,
    pub(super) months: i64,
    pub(super) grain: Grain,
    pub(super) date_only: bool,
    pub(super) expected_horizon: Scalar,
}
