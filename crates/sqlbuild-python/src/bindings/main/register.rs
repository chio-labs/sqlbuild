use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::pymodule;
use sqlbuild_rules::constants::{API_VERSION, NATIVE_BUILD_IDENTITY};

use crate::bindings::_helpers::boundary::panics::NativeCompilerError;
use crate::bindings::_helpers::{analysis, boundary, discovery, rules, scopes, sqltext};
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
    sqltext::model_headers::register(module)?;
    sqltext::static_sql::register(module)?;
    boundary::oracles::register(module)?;
    discovery::project_files::register(module)?;
    scopes::scope_index::register(module)?;
    module.add("API_VERSION", API_VERSION)?;
    module.add("BUILD_IDENTITY", NATIVE_BUILD_IDENTITY)?;
    Ok(())
}
