//! Extract, plan and render SQL tests natively.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;
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

/// The scenario extraction outcome as JSON.
#[pyfunction]
fn extract_sql_scenario_json(
    py: Python<'_>,
    sql: &str,
    file_label: &str,
    syntax: LexicalSyntaxInput,
) -> PyResult<String> {
    let syntax: LexicalSyntax = syntax.into();
    py.compiler_detach(|| {
        sqlbuild_analysis::compiler::main::sql_scenario_extraction::extract_scenario_json(
            sql, file_label, &syntax,
        )
    })
    .map_err(value_error)
}

/// The error for a function type the adapter's SQL analysis dialect cannot parse, or `None`.
#[pyfunction]
fn function_type_error(
    py: Python<'_>,
    type_sql: &str,
    adapter_name: &str,
    context: &str,
) -> PyResult<Option<String>> {
    py.compiler_detach(|| {
        Ok::<_, String>(
            sqlbuild_analysis::compiler::main::function_type_validation::function_type_error(
                type_sql,
                adapter_name,
                context,
            ),
        )
    })
    .map_err(value_error)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(function_type_error, module)?)?;
    module.add_function(wrap_pyfunction!(extract_sql_scenario_json, module)?)?;
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
