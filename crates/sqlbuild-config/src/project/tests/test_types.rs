use crate::errors::ConfigErrorKind;
use crate::project::models::{LocalConfigFile, ProjectConfigFile};

pub(super) struct ProjectConfigTestCase {
    pub(super) description: &'static str,
    pub(super) files: &'static [(&'static str, &'static str)],
    pub(super) expected_config: Result<ProjectConfigFile, ConfigErrorKind>,
}

pub(super) struct LocalConfigTestCase {
    pub(super) description: &'static str,
    pub(super) files: &'static [(&'static str, &'static str)],
    pub(super) expected_config: Result<LocalConfigFile, ConfigErrorKind>,
}
