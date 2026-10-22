//! Register the native model configuration functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::model_config::{
    config_errors, config_values, header_columns, model_config_builder, model_validator,
    template_data, unicode_environment,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    config_errors::register(module)?;
    config_values::register(module)?;
    header_columns::register(module)?;
    model_config_builder::register(module)?;
    model_validator::register(module)?;
    template_data::register(module)?;
    unicode_environment::register(module)?;
    Ok(())
}
