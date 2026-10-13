//! Register the static `sqb dbt` interop helpers.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::dbt_interop::profile;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    profile::register(module)
}
