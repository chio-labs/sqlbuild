//! What a path default's models inherit.

use crate::model_config_build::_helpers::layers::{
    layered_own, path_default_values, project_defaults,
};
use crate::model_config_build::models::ConfigBuildInputs;
use crate::model_config_build::types::{ConfigBuildHost, HostEntries, HostHalt};

/// `build_layered_model_values` with an empty header: the defaults under the matched path default.
pub fn inherited_config<B: ConfigBuildHost>(
    (host, inputs): (&B, &ConfigBuildInputs<B::Handle>),
    matched_path_default: Option<&str>,
) -> Result<HostEntries<B>, HostHalt<B>> {
    let mut layered = project_defaults(inputs);
    if let Some(key) = matched_path_default {
        layered = layered_own(host, &layered, path_default_values(inputs, key)?)?.0;
    }
    Ok(layered)
}
