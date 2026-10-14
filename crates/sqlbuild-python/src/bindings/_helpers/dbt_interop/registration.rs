//! Register the static `sqb dbt` interop helpers.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::dbt_interop::{cli, graph, manifest, orchestration, plan, profile};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    cli::register(module)?;
    graph::register(module)?;
    manifest::register(module)?;
    orchestration::register(module)?;
    plan::register(module)?;
    profile::register(module)
}
