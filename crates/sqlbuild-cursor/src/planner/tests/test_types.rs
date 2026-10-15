use crate::algebra::models::{Grain, Scalar};
use crate::planner::models::CursorEndClamp;

pub(super) struct HorizonTestCase {
    pub(super) description: &'static str,
    pub(super) months: i64,
    pub(super) grain: Grain,
    pub(super) date_only: bool,
    pub(super) expected_horizon: Scalar,
}

pub(super) struct UtcZones;

pub(super) struct RollingWindowTestCase {
    pub(super) description: &'static str,
    pub(super) days: i64,
    pub(super) grain: Grain,
    pub(super) expected_window: (Scalar, Scalar),
}

pub(super) struct CursorEndClampTestCase {
    pub(super) description: &'static str,
    pub(super) start_day: u32,
    pub(super) end_day: u32,
    pub(super) expected_clamp: CursorEndClamp,
}
