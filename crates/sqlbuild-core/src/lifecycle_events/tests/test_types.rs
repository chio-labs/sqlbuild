use crate::lifecycle_events::models::KnownEventFacts;

pub(crate) struct ValidateTestCase {
    pub(crate) description: &'static str,
    pub(crate) event: KnownEventFacts,
    pub(crate) expected_result: Result<(), &'static str>,
}
