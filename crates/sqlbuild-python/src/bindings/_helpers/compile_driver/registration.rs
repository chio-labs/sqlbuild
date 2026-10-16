//! Register the native compile command driver.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::wrap_pyfunction;

use crate::bindings::_helpers::compile_driver::{
    analysis, analysis_cache, assembly, command, deferral, diagnostic_collector, diff, discovery,
    input_reads, inputs, pipeline, pipeline_entries, plan_result, project, python_plan_entries,
    relation_targets, selection_phases, stage_work, targets,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    analysis::register(module)?;
    analysis_cache::register(module)?;
    assembly::register(module)?;
    command::register(module)?;
    project::register(module)?;
    inputs::register(module)?;
    input_reads::register(module)?;
    discovery::register(module)?;
    pipeline::register(module)?;
    pipeline_entries::register(module)?;
    plan_result::register(module)?;
    deferral::register(module)?;
    diagnostic_collector::register(module)?;
    diff::register(module)?;
    python_plan_entries::register(module)?;
    relation_targets::register(module)?;
    selection_phases::register(module)?;
    module.add_function(wrap_pyfunction!(
        stage_work::compile_stage_work_info,
        module
    )?)?;
    targets::register(module)
}
