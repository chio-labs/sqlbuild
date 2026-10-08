use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::pymodule;
use sqlbuild_rules::constants::{API_VERSION, NATIVE_BUILD_IDENTITY};

use crate::bindings::_helpers::boundary::panics::NativeCompilerError;
use crate::bindings::_helpers::{
    analysis, analysis_session, attachments, boundary, cache, contracts, discovery, lineage,
    model_config, project_assembly, render, rules, scopes, semantic_checks, sql_test_glue, sqltext,
    type_system,
};
use crate::bindings::models;

#[pymodule]
pub fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    rules::evaluation::register(module)?;
    rules::lint::register(module)?;
    rules::skills::register(module)?;
    module.add_class::<models::ParsedRulesRequest>()?;
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
    render::macro_calls::register(module)?;
    cache::native_store::register(module)?;
    attachments::registration::register(module)?;
    register_analysis_stages(module)?;
    module.add("API_VERSION", API_VERSION)?;
    module.add("BUILD_IDENTITY", NATIVE_BUILD_IDENTITY)?;
    Ok(())
}

fn register_analysis_stages(module: &Bound<'_, PyModule>) -> PyResult<()> {
    type_system::registration::register(module)?;
    analysis_session::registration::register(module)?;
    semantic_checks::registration::register(module)?;
    contracts::registration::register(module)?;
    lineage::registration::register(module)?;
    sql_test_glue::registration::register(module)?;
    project_assembly::registration::register(module)?;
    Ok(())
}
