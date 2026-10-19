//! `load_rules_config`: the validated `[rules]` configuration of one project.

use std::path::Path;

use crate::configuration::errors::RulesConfigLoadError;
use crate::models::RulesConfig;

/// The project's rules configuration, or the reason it cannot be loaded.
pub fn load_rules_config(project_dir: &Path) -> Result<RulesConfig, RulesConfigLoadError> {
    crate::configuration::_helpers::loading::load(project_dir)
}
