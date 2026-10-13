use crate::algebra::errors::CursorError;
use crate::algebra::models::{DurationSpan, Grain, Moment, Scalar};

/// Zone rules for values that never carry an external zone.
pub(crate) struct NoZones;

pub(crate) struct StepTestCase {
    pub(crate) description: &'static str,
    pub(crate) value: Scalar,
    pub(crate) grain: Grain,
    pub(crate) expected_floor: Scalar,
    pub(crate) expected_next: Result<Scalar, CursorError>,
}

pub(crate) struct SplitTestCase {
    pub(crate) description: &'static str,
    pub(crate) start: Scalar,
    pub(crate) end: Scalar,
    pub(crate) grain: Option<Grain>,
    pub(crate) step: i64,
    pub(crate) expected_starts: Result<Vec<String>, CursorError>,
}

pub(crate) struct DurationTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) expected_digits: Option<[&'static str; 6]>,
}

pub(crate) struct ShiftTestCase {
    pub(crate) description: &'static str,
    pub(crate) moment: Moment,
    pub(crate) span: DurationSpan,
    pub(crate) direction: i64,
    pub(crate) expected_moment: Result<Moment, CursorError>,
}

pub(crate) struct TextTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) expected_text: &'static str,
}

pub(crate) struct RenderTestCase {
    pub(crate) description: &'static str,
    pub(crate) value: Scalar,
    pub(crate) expected_text: Result<String, CursorError>,
}
