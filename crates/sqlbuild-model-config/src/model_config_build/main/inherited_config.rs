//! What a path default's models inherit.

use crate::config_values::types::ConfigEntries;
use crate::model_config_build::_helpers::layers::{
    layered_own, path_default_values, project_defaults,
};
use crate::model_config_build::models::{ConfigBuildHalt, ConfigBuildInputs};

/// `build_layered_model_values` with an empty header: the defaults under the matched path default.
pub fn inherited_config<H: Clone, E>(
    inputs: &ConfigBuildInputs<H>,
    matched_path_default: Option<&str>,
) -> Result<ConfigEntries<H>, ConfigBuildHalt<H, E>> {
    let mut layered = project_defaults(inputs);
    if let Some(key) = matched_path_default {
        layered = layered_own(&layered, path_default_values(inputs, key)?).0;
    }
    Ok(layered)
}
