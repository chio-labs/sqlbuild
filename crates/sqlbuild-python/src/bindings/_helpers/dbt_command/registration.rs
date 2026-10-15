//! Register the native `sqb dbt` commands.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::dbt_command::{command, init, init_project};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    command::register(module)?;
    init::register(module)?;
    init_project::register(module)
}
