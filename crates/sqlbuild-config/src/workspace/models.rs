//! Requests to create a playground or install skills, and maintenance outcomes.

use std::path::PathBuf;

/// Where `sqb skills` installs, from where, and how.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SkillInstallRequest {
    pub project_dir: PathBuf,
    /// The packaged `.agents/skills/sqlbuild` directory.
    pub skills_root: PathBuf,
    pub home_dir: PathBuf,
    pub global_install: bool,
    pub requested_targets: Vec<String>,
    pub force: bool,
}

/// One playground to create from the packaged templates.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PlaygroundRequest {
    /// The packaged `playground_templates` directory.
    pub templates_root: PathBuf,
    pub target_dir: PathBuf,
    pub template: String,
}
