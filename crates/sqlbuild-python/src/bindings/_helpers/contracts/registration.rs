//! Register the native contract functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::contracts::{
    contract_diagnostics, effective_config, exception_types, project_config, resource_identities,
    spec_resolution, sql_values, state_literals,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    contract_diagnostics::register(module)?;
    effective_config::register(module)?;
    exception_types::register(module)?;
    project_config::register(module)?;
    resource_identities::register(module)?;
    spec_resolution::register(module)?;
    sql_values::register(module)?;
    state_literals::register(module)
}
