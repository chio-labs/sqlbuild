use crate::test_targets::models::{ScenarioCteSources, TestTargets};

pub(super) struct UnknownTargetTestCase {
    pub(super) description: &'static str,
    pub(super) targets: TestTargets,
    pub(super) expected_error: Option<&'static str>,
}

pub(super) struct ScenarioSourceTestCase {
    pub(super) description: &'static str,
    pub(super) ctes: Vec<ScenarioCteSources>,
    pub(super) expected_error: Option<&'static str>,
}
