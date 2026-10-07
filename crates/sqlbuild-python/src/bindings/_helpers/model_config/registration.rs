//! Register the native model configuration functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::model_config::{config_presence, config_templates, header_metadata};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    header_metadata::register(module)?;
    config_presence::register(module)?;
    config_templates::register(module)?;
    Ok(())
}
