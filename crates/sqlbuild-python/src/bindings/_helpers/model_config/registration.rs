//! Register the native model configuration functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::model_config::{
    column_migrations, config_errors, config_templates, described_models, model_config_builder,
    model_validator,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    column_migrations::register(module)?;
    config_errors::register(module)?;
    config_templates::register(module)?;
    described_models::register(module)?;
    model_config_builder::register(module)?;
    model_validator::register(module)?;
    Ok(())
}
