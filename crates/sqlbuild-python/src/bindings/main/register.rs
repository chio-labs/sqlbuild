use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::pymodule;
use sqlbuild_rules::constants::{API_VERSION, NATIVE_BUILD_IDENTITY};

use crate::bindings::_helpers::boundary::panics::NativeCompilerError;
use crate::bindings::_helpers::{
    analysis, analysis_session, attachments, auditing, authored_values, boundary, cache, cli,
    compile_attachment, compile_command, compile_driver, compile_outputs, compiled_project,
    contracts, cost_report, dag_artifact, discovery, fingerprints, frontier, graph, lineage,
    macro_bridge, manifest, model_config, plan_output, presentation_text, project_assembly,
    refactor, references, render, result_output, rules, scopes, semantic_checks, semantic_shapes,
    sql_test_glue, sqltext, type_system, workspace_commands,
};
use crate::bindings::models;

#[pymodule]
pub fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    rules::registration::register(module)?;
    cli::registration::register(module)?;
    module.add(
        "NativeCompilerError",
        module.py().get_type::<NativeCompilerError>(),
    )?;
    module.add_class::<models::ProjectCatalog>()?;
    module.add_class::<models::CompactAnalysisJob>()?;
    module.add_class::<models::BindingPositions>()?;
    analysis::normalization::register(module)?;
    analysis::queries::register(module)?;
    analysis::sql_tests::register(module)?;
    sqltext::registration::register(module)?;
    boundary::oracles::register(module)?;
    discovery::registration::register(module)?;
    scopes::registration::register(module)?;
    model_config::registration::register(module)?;
    render::registration::register(module)?;
    register_project_stages(module)?;
    register_analysis_stages(module)?;
    module.add("API_VERSION", API_VERSION)?;
    module.add("BUILD_IDENTITY", NATIVE_BUILD_IDENTITY)?;
    Ok(())
}

fn register_project_stages(module: &Bound<'_, PyModule>) -> PyResult<()> {
    cache::registration::register(module)?;
    attachments::registration::register(module)?;
    refactor::registration::register(module)?;
    plan_output::registration::register(module)?;
    references::registration::register(module)?;
    authored_values::registration::register(module)?;
    result_output::registration::register(module)?;
    cost_report::registration::register(module)?;
    presentation_text::registration::register(module)?;
    workspace_commands::registration::register(module)?;
    auditing::registration::register(module)?;
    Ok(())
}

fn register_analysis_stages(module: &Bound<'_, PyModule>) -> PyResult<()> {
    type_system::registration::register(module)?;
    analysis_session::registration::register(module)?;
    semantic_checks::registration::register(module)?;
    semantic_shapes::registration::register(module)?;
    contracts::registration::register(module)?;
    lineage::registration::register(module)?;
    fingerprints::registration::register(module)?;
    sql_test_glue::registration::register(module)?;
    project_assembly::registration::register(module)?;
    compile_outputs::registration::register(module)?;
    graph::registration::register(module)?;
    compiled_project::registration::register(module)?;
    compile_attachment::registration::register(module)?;
    compile_command::registration::register(module)?;
    compile_driver::registration::register(module)?;
    frontier::registration::register(module)?;
    macro_bridge::registration::register(module)?;
    dag_artifact::registration::register(module)?;
    manifest::registration::register(module)?;
    Ok(())
}
