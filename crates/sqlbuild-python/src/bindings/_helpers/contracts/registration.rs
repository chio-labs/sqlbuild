//! Register the native contract functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::contracts::{
    dynamic_names, effective_config, model_contracts, project_config, resource_identities,
    sql_values,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    model_contracts::register(module)?;
    dynamic_names::register(module)?;
    effective_config::register(module)?;
    project_config::register(module)?;
    resource_identities::register(module)?;
    sql_values::register(module)
}
