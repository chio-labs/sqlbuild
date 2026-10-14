//! Fixture schema conversion at the Python model boundary.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_rules::lint_text::main::simplify_fixture_nulls::simplify_fixture_nulls;

use crate::bindings::_helpers::boundary::panics::{compiler_guard, value_error};

#[pyfunction]
#[pyo3(signature = (*, sql, relation))]
fn simplify_fixture_null_projections(sql: &str, relation: &Bound<'_, PyAny>) -> PyResult<String> {
    let columns: Vec<(String, Option<String>, Option<bool>)> = relation
        .getattr("columns")?
        .try_iter()?
        .map(|column| {
            let column = column?;
            Ok((
                column.getattr("name")?.extract()?,
                column.getattr("type")?.extract()?,
                column.getattr("nullable")?.extract()?,
            ))
        })
        .collect::<PyResult<_>>()?;
    compiler_guard(|| simplify_fixture_nulls(sql, &columns).map_err(value_error))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(simplify_fixture_null_projections, module)?)
}
