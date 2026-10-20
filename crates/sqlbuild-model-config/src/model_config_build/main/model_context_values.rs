//! The context values hook templates read for one model's built config.

use crate::config_values::models::ConfigNode;
use crate::config_values::types::ConfigEntries;
use crate::config_values::types::HostObject;
use crate::model_config_build::_helpers::context::model_context;
use crate::model_config_build::models::ConfigBuildInputs;

/// `build_model_context_values` for a model's config values.
#[must_use]
pub fn model_context_values<H: HostObject>(
    inputs: &ConfigBuildInputs<H>,
    values: &[(ConfigNode<H>, ConfigNode<H>)],
    model_name: &str,
    include_target_values: bool,
) -> ConfigEntries<H> {
    model_context(inputs, values, model_name, include_target_values)
}
