use crate::project::errors::ConfigFailure;

pub(super) struct ProjectFailureTestCase {
    pub(super) description: &'static str,
    pub(super) project: &'static str,
    pub(super) local: &'static str,
    pub(super) expected_failure: Option<ConfigFailure>,
}
