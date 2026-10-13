//! Register the native compile command driver.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::compile_driver::{
    analysis, assembly, command, discovery, inputs, pipeline, pipeline_entries, project, targets,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    analysis::register(module)?;
    assembly::register(module)?;
    command::register(module)?;
    project::register(module)?;
    inputs::register(module)?;
    discovery::register(module)?;
    pipeline::register(module)?;
    pipeline_entries::register(module)?;
    targets::register(module)
}
