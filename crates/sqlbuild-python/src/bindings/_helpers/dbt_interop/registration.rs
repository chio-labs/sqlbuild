//! Register the static `sqb dbt` interop helpers.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::dbt_interop::{graph, manifest, plan, profile};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    graph::register(module)?;
    manifest::register(module)?;
    plan::register(module)?;
    profile::register(module)
}
