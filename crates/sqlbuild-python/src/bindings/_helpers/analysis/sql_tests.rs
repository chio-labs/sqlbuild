//! Extract, plan and render SQL tests natively.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use sqlbuild_core::panics::main::native_failure::native_failure;

use crate::bindings::_helpers::boundary::panics::{compiler_error, value_error};
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;
use crate::bindings::types::CompilerDetach;

const HELPER_READS_CONTEXT: &str = "native SQL-test helper reads";

#[pyfunction]
fn render_sql_test_comparisons_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_analysis::compiler::main::sql_test_rendering::render_json(request_json)
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

/// Python's `_parsed_reads`: the helper keys a CTE body reads, or None if it does not parse.
#[pyfunction]
fn sql_test_helper_reads(
    py: Python<'_>,
    sql: &str,
    keys: Vec<String>,
) -> PyResult<Option<Vec<String>>> {
    py.compiler_detach(|| {
        sqlbuild_analysis::assembly::analysis_session::main::sql_test_helper_reads::sql_test_helper_reads(
            sql, &keys,
        )
            .map_err(|reason| native_failure(HELPER_READS_CONTEXT, &reason))
    })
    .map_err(compiler_error)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(sql_test_helper_reads, module)?)?;
    module.add_function(wrap_pyfunction!(extract_sql_scenario_json, module)?)?;
    module.add_function(wrap_pyfunction!(render_sql_test_comparisons_json, module)?)?;
    module.add_function(wrap_pyfunction!(
        render_sql_test_difference_sample_json,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(extract_sql_tests_json, module)?)?;
    Ok(())
}
