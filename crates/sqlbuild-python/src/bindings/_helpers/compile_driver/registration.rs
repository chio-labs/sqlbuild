//! Register the native compile command driver.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::compile_driver::{
    analysis, assembly, command, deferral, diff, discovery, inputs, pipeline, pipeline_entries,
    project, python_plan_entries, relation_targets, targets,
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
    deferral::register(module)?;
    diff::register(module)?;
    python_plan_entries::register(module)?;
    relation_targets::register(module)?;
    targets::register(module)
}
