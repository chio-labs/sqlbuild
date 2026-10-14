//! Register the native compile command driver.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::compile_driver::{
    analysis, assembly, command, deferral, diff, discovery, input_reads, inputs, pipeline,
    pipeline_entries, project, python_plan_entries, relation_targets, selection_phases, targets,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    analysis::register(module)?;
    assembly::register(module)?;
    command::register(module)?;
    project::register(module)?;
    inputs::register(module)?;
    input_reads::register(module)?;
    discovery::register(module)?;
    pipeline::register(module)?;
    pipeline_entries::register(module)?;
    deferral::register(module)?;
    diff::register(module)?;
    python_plan_entries::register(module)?;
    relation_targets::register(module)?;
    selection_phases::register(module)?;
    targets::register(module)
}
