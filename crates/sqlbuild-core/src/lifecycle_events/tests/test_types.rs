use crate::lifecycle_events::models::{HookFacts, KnownEventFacts, SequenceFact};

pub(crate) struct ValidateTestCase {
    pub(crate) description: &'static str,
    pub(crate) event: KnownEventFacts,
    pub(crate) expected_result: Result<(), &'static str>,
}

pub(crate) struct LifecycleVersionTestCase {
    pub(crate) description: &'static str,
    pub(crate) schema_version: i128,
    pub(crate) sequence: SequenceFact,
    pub(crate) has_external_context: bool,
    pub(crate) expected_problem: Option<&'static str>,
}

pub(crate) struct RunBoundsTestCase {
    pub(crate) description: &'static str,
    pub(crate) counts: (i128, i128, i128),
    pub(crate) expected_problem: Option<&'static str>,
}

pub(crate) struct HookTestCase {
    pub(crate) description: &'static str,
    pub(crate) hook: HookFacts<'static>,
    pub(crate) expected_problem: Option<&'static str>,
}
