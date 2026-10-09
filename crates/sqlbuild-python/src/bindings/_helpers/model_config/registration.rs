//! Register the native model configuration functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::model_config::{
    config_errors, config_templates, header_metadata, model_config_builder, model_validator,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    config_errors::register(module)?;
    header_metadata::register(module)?;
    config_templates::register(module)?;
    model_config_builder::register(module)?;
    model_validator::register(module)?;
    Ok(())
}
