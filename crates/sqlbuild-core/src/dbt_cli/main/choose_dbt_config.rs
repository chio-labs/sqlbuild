//! Choose dbt settings from CLI overrides, local config and project config.

use crate::dbt_cli::constants::{MISSING_PROJECT_DIR_HELP, MISSING_PROJECT_DIR_MESSAGE};
use crate::dbt_cli::errors::DbtCliError;
use crate::dbt_cli::models::{DbtConfigChoice, DbtConfigSources};

/// CLI overrides win over project config; `target` also consults local config first.
pub fn choose_dbt_config(
    sources: DbtConfigSources,
    require_project_dir: bool,
) -> Result<DbtConfigChoice, DbtCliError> {
    let project_dir: Option<String> = sources.override_project_dir.or(sources.config_project_dir);
    if require_project_dir && project_dir.is_none() {
        return Err(DbtCliError {
            message: MISSING_PROJECT_DIR_MESSAGE.to_owned(),
            code: None,
            help: Some(MISSING_PROJECT_DIR_HELP),
        });
    }
    Ok(DbtConfigChoice {
        project_dir,
        profiles_dir: sources
            .override_profiles_dir
            .or(sources.config_profiles_dir),
        target_path: sources.override_target_path.or(sources.config_target_path),
        target: sources
            .override_target
            .or(sources.local_target)
            .or(sources.config_target),
    })
}
