//! Native type normalization for the preview type system.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::type_system::main::normalize_type::normalize_type;
use sqlbuild_analysis::type_system::models::{NormalizedType, TypeNormalization};

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// `(name, family, precision, scale, length)` of one normalized type.
type NormalizedRow = (String, &'static str, Option<i64>, Option<i64>, Option<i64>);

/// Normalize one type: `(normalized row, Polyglot parse error)`, or None to defer to Python.
#[pyfunction]
#[pyo3(name = "normalize_type")]
fn normalize_type_binding(
    type_sql: &str,
    dialect: &str,
) -> PyResult<Option<(NormalizedRow, Option<String>)>> {
    compiler_guard(|| {
        Ok(normalize_type(type_sql, dialect).map(
            |TypeNormalization {
                 normalized,
                 parse_error,
             }| (normalized_row(normalized), parse_error),
        ))
    })
}

fn normalized_row(normalized: NormalizedType) -> NormalizedRow {
    (
        normalized.normalized_name,
        normalized.family.as_str(),
        normalized.precision,
        normalized.scale,
        normalized.length,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(normalize_type_binding, module)?)?;
    Ok(())
}
