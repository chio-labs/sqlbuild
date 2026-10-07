//! Extract, plan and render SQL tests natively.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::types::CompilerDetach;

#[pyfunction]
fn render_sql_test_comparisons_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_analysis::compiler::main::sql_test_rendering::render_json(request_json)
    })
    .map_err(value_error)
}

#[pyfunction]
fn plan_and_render_sql_tests_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_analysis::compiler::main::sql_test_planning::plan_and_render_json(request_json)
    })
    .map_err(value_error)
}

#[pyfunction]
fn resolve_sql_test_chains_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_analysis::compiler::main::sql_test_chain_resolution::resolve_chains_json(
            request_json,
        )
    })
    .map_err(value_error)
}

#[pyfunction]
fn render_sql_test_difference_sample_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_analysis::compiler::main::sql_test_difference_sampling::render_difference_sample_json(
            request_json,
        )
    })
    .map_err(value_error)
}

#[pyfunction]
fn extract_sql_tests_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_analysis::compiler::main::sql_test_extraction::extract_batch_json(request_json)
    })
    .map_err(value_error)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(render_sql_test_comparisons_json, module)?)?;
    module.add_function(wrap_pyfunction!(plan_and_render_sql_tests_json, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_sql_test_chains_json, module)?)?;
    module.add_function(wrap_pyfunction!(
        render_sql_test_difference_sample_json,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(extract_sql_tests_json, module)?)?;
    Ok(())
}
