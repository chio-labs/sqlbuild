use serde_json::Value;

use crate::janitor_planning::models::ArchiveTimestamp;
use crate::review_command::models::{DownstreamPolicy, ReviewReport, SelectedToken};

pub(super) struct PlanTestCase {
    pub(super) description: &'static str,
    pub(super) changed: Vec<&'static str>,
    pub(super) policy: DownstreamPolicy,
    pub(super) select: Option<Vec<SelectedToken>>,
    pub(super) expected_validated: Vec<&'static str>,
    pub(super) expected_not_validated: Vec<(&'static str, &'static str)>,
    /// `(node, the validated node that depends on it)`.
    pub(super) expected_added: Vec<(&'static str, &'static str)>,
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
    pub(super) expected_status: &'static str,
    pub(super) expected_exit_code: i32,
}

pub(super) struct JsonTestCase {
    pub(super) description: &'static str,
    pub(super) report: ReviewReport,
    pub(super) expected_values: Vec<(&'static str, Value)>,
}

pub(super) struct PolicyTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) expected_policy: Option<DownstreamPolicy>,
}

pub(super) struct SchemaNameBuildTestCase {
    pub(super) description: &'static str,
    pub(super) parts: (&'static str, &'static str, &'static str, &'static str),
    pub(super) expected_name: &'static str,
}

pub(super) struct RenderTestCase {
    pub(super) description: &'static str,
    pub(super) report: ReviewReport,
    pub(super) expected_fragments: Vec<&'static str>,
    pub(super) unexpected_fragments: Vec<&'static str>,
}

pub(super) struct SchemaNameTestCase {
    pub(super) description: &'static str,
    pub(super) name: &'static str,
    pub(super) expected_timestamp: Option<ArchiveTimestamp>,
}

pub(super) struct HooksTestCase {
    pub(super) description: &'static str,
    pub(super) changed: Vec<&'static str>,
    pub(super) expected_hooks: Vec<&'static str>,
}
