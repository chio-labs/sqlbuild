//! Lint and format SQL with the native rules engine.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{FromPyObject, pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::panics::{compiler_guard, value_error};
use crate::bindings::types::CompilerDetach;

#[pyfunction]
fn lint_sql_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| sqlbuild_rules::sql_lint::main::engine::lint_json(request_json))
        .map_err(value_error)
}

/// One SQL lint preparation request, read from a Python mapping.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct LintPreparationRequest {
    expanded: String,
    before_expansion: String,
    prior_sites: Vec<usize>,
    dialect: String,
}

#[pyfunction]
fn prepare_lint_sql(
    py: Python<'_>,
    request: LintPreparationRequest,
) -> PyResult<Option<sqlbuild_rules::sql_lint::types::PreparedSql>> {
    py.compiler_detach(|| {
        sqlbuild_rules::sql_lint::main::preparation::prepare(
            &request.expanded,
            &request.before_expansion,
            &request.prior_sites,
            &request.dialect,
        )
    })
    .map_err(value_error)
}

/// Prepare many bodies in one detached call; `false` marks a body to prepare again individually.
#[pyfunction]
fn prepare_lint_sql_batch(
    py: Python<'_>,
    requests: Vec<LintPreparationRequest>,
) -> PyResult<Vec<(bool, Option<sqlbuild_rules::sql_lint::types::PreparedSql>)>> {
    py.compiler_detach(|| {
        Ok(requests
            .iter()
            .map(|request| {
                sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic(|| {
                    sqlbuild_rules::sql_lint::main::preparation::prepare(
                        &request.expanded,
                        &request.before_expansion,
                        &request.prior_sites,
                        &request.dialect,
                    )
                })
                .map_or((false, None), |prepared| (true, prepared))
            })
            .collect())
    })
    .map_err(value_error)
}

#[pyfunction]
fn lint_backtick_identifiers(dialect: &str) -> PyResult<bool> {
    compiler_guard(|| {
        Ok(sqlbuild_rules::sql_lint::main::backtick_identifiers::backtick_identifiers(dialect))
    })
}

#[pyfunction]
fn lint_sql_batch_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_rules::sql_lint::main::batch_engine::lint_batch_json(request_json)
    })
    .map_err(value_error)
}

#[pyfunction]
fn format_sql_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| sqlbuild_rules::sql_lint::main::formatter::format_json(request_json))
        .map_err(value_error)
}

#[pyfunction]
fn format_sql_batch_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.compiler_detach(|| {
        sqlbuild_rules::sql_lint::main::batch_formatter::format_batch_json(request_json)
    })
    .map_err(value_error)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(lint_sql_json, module)?)?;
    module.add_function(wrap_pyfunction!(prepare_lint_sql, module)?)?;
    module.add_function(wrap_pyfunction!(prepare_lint_sql_batch, module)?)?;
    module.add_function(wrap_pyfunction!(lint_backtick_identifiers, module)?)?;
    module.add_function(wrap_pyfunction!(lint_sql_batch_json, module)?)?;
    module.add_function(wrap_pyfunction!(format_sql_json, module)?)?;
    module.add_function(wrap_pyfunction!(format_sql_batch_json, module)?)?;
    Ok(())
}
