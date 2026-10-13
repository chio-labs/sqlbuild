use crate::dbt_profile::errors::DbtProfileError;
use crate::dbt_profile::models::{DbtInitConfig, NormalizedProfile, ProfileEntry};

pub(super) struct NormalizeTestCase {
    pub(super) description: &'static str,
    pub(super) entries: Vec<ProfileEntry>,
    pub(super) expected_result: Result<NormalizedProfile, DbtProfileError>,
}

pub(super) struct InitTomlTestCase {
    pub(super) description: &'static str,
    pub(super) config: DbtInitConfig,
    pub(super) expected_toml: &'static str,
}
