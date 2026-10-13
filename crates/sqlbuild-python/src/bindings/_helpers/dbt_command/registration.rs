//! Register the native `sqb dbt` commands.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::dbt_command::{command, init};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    command::register(module)?;
    init::register(module)
}
