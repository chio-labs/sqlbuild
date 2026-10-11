//! Register the native contract functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::contracts::{effective_config, model_contracts, project_config};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    model_contracts::register(module)?;
    effective_config::register(module)?;
    project_config::register(module)
}
