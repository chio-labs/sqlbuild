use crate::project::errors::ConfigFailure;

pub(super) struct ProjectFailureTestCase {
    pub(super) description: &'static str,
    pub(super) project: &'static str,
    pub(super) local: &'static str,
    pub(super) expected_failure: Option<ConfigFailure>,
}

pub(super) struct GuidanceTestCase {
    pub(super) description: &'static str,
    pub(super) rendered: (String, String),
    pub(super) expected_note: &'static str,
    pub(super) expected_help: &'static str,
}
