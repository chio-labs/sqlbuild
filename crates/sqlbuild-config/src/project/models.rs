//! The project configuration fields native discovery reads.

use crate::models::ConfigValue;

/// Shared settings discovery reads from `[settings]`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProjectSettings {
    pub sql_analysis: bool,
    pub require_sql_analysis: bool,
}

/// The discovery fields of `sqlbuild_project.toml`, with Python's defaults and stripping.
#[derive(Clone, Debug, PartialEq)]
pub struct ProjectConfigFile {
    pub name: String,
    pub adapter: String,
    pub default_target: Option<String>,
    pub settings: ProjectSettings,
    pub enforce_placement: bool,
    pub enforce_explicit_references: bool,
    pub vars: Vec<(String, String)>,
    pub path_defaults: Vec<(String, ConfigValue)>,
    pub target_names: Vec<String>,
}

/// The discovery fields of `sqlbuild_local.toml`; an absent file reads as the default.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct LocalConfigFile {
    pub target: Option<String>,
    pub adapter: Option<String>,
    pub sql_analysis: Option<bool>,
    pub vars: Vec<(String, String)>,
    pub target_names: Vec<String>,
}
