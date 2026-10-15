use crate::dbt_profile::errors::DbtProfileError;
use crate::dbt_profile::models::{
    DbtInitConfig, DbtProfileOutputs, DbtProjectMetadata, DbtYamlValue, LoadedDbtProfile,
    NormalizedProfile, ProfileEntry,
};

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

pub(super) struct ProjectMetadataTestCase {
    pub(super) description: &'static str,
    pub(super) values: [DbtYamlValue; 3],
    pub(super) expected_result: Result<DbtProjectMetadata, DbtProfileError>,
}

pub(super) struct ProfileOutputsTestCase {
    pub(super) description: &'static str,
    pub(super) loaded: LoadedDbtProfile,
    pub(super) expected_result: Result<DbtProfileOutputs, DbtProfileError>,
}

pub(super) struct SelectTargetTestCase {
    pub(super) description: &'static str,
    pub(super) profile: DbtProfileOutputs,
    pub(super) requested: Option<&'static str>,
    pub(super) expected_result: Result<(String, usize), DbtProfileError>,
}
