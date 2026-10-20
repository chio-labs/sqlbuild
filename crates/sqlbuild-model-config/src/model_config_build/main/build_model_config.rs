//! One model's effective config built from its layers, as `build_model_config` builds it.

use crate::model_config_build::_helpers::checks::check_header_tags;
use crate::model_config_build::_helpers::phases::{
    BuildModel, Layered, finished, layered, model_templates, targeted,
};
use crate::model_config_build::models::{
    BuiltModelConfig, ConfigBuildHalt, ConfigBuildInputs, ModelHeader,
};
use crate::model_config_build::types::{ConfigBuildHost, HostHalt};

/// One model's effective config: its layers merged, then expanded for the model and its target.
pub fn build_model_config<B: ConfigBuildHost>(
    (host, inputs): (&B, &ConfigBuildInputs<B::Handle>),
    header: ModelHeader<'_, B::Handle>,
    matched_path_default: Option<&str>,
    name: &str,
) -> Result<BuiltModelConfig<B::Handle>, HostHalt<B>> {
    check_header_tags(header.entries, name).map_err(ConfigBuildHalt::Config)?;
    let model: BuildModel<'_, B> = BuildModel {
        host,
        inputs,
        header,
        name,
    };
    let Layered {
        mut phase,
        set_aside,
        has_templates,
    } = layered(&model, matched_path_default)?;
    if has_templates {
        phase = model_templates(&model, phase)?;
    }
    let targeted = targeted(&model, phase, has_templates)?;
    finished(&model, set_aside, targeted)
}
