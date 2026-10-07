//! Substitute static project variables and extract static SQL references.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::panics::compiler_guard;

#[pyfunction]
fn substitute_static_project_vars(
    sqls: Vec<String>,
    variables: Vec<(String, String)>,
) -> PyResult<Vec<(u8, Option<String>)>> {
    compiler_guard(|| {
        Ok(
            sqlbuild_sqltext::compiler::main::sql_interpolation::substitute_batch(
                &sqls, &variables,
            ),
        )
    })
}

#[pyfunction]
fn extract_static_sql_references(
    sql: &str,
) -> PyResult<Option<Vec<sqlbuild_sqltext::compiler::types::StaticReference>>> {
    compiler_guard(|| {
        Ok(sqlbuild_sqltext::compiler::main::sql_references::extract(
            sql,
        ))
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(substitute_static_project_vars, module)?)?;
    module.add_function(wrap_pyfunction!(extract_static_sql_references, module)?)?;
    Ok(())
}
