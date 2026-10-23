use crate::review_command::models::{DownstreamPolicy, ReviewReport, SelectedToken};

pub(super) struct PlanTestCase {
    pub(super) description: &'static str,
    pub(super) changed: Vec<&'static str>,
    pub(super) policy: DownstreamPolicy,
    pub(super) select: Option<Vec<SelectedToken>>,
    pub(super) expected_validated: Vec<&'static str>,
    pub(super) expected_not_validated: Vec<(&'static str, &'static str)>,
}

pub(super) struct PlanErrorTestCase {
    pub(super) description: &'static str,
    pub(super) policy: DownstreamPolicy,
    pub(super) select: Vec<SelectedToken>,
    pub(super) expected_code: &'static str,
    pub(super) expected_fragment: &'static str,
}

pub(super) struct OutcomeTestCase {
    pub(super) description: &'static str,
    pub(super) report: ReviewReport,
    pub(super) expected: (&'static str, i32),
}

pub(super) struct RenderTestCase {
    pub(super) description: &'static str,
    pub(super) report: ReviewReport,
    pub(super) expected_fragments: Vec<&'static str>,
}

pub(super) struct SchemaNameTestCase {
    pub(super) description: &'static str,
    pub(super) name: &'static str,
    pub(super) expected: Option<(i32, u32, u32, u32, u32, u32)>,
}
