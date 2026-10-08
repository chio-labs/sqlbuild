use crate::test_targets::models::{ScenarioCteSources, TargetGroup};

pub(super) struct UnknownTargetTestCase {
    pub(super) description: &'static str,
    pub(super) groups: Vec<TargetGroup>,
    pub(super) expected_error: Option<&'static str>,
}

pub(super) struct ScenarioSourceTestCase {
    pub(super) description: &'static str,
    pub(super) ctes: Vec<ScenarioCteSources>,
    pub(super) expected_error: Option<&'static str>,
}
