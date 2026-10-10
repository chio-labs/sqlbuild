//! Native type normalization.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::type_system::main::normalize_type::normalize_type;
use sqlbuild_analysis::type_system::models::{
    NormalizedType, TypeNormalization, TypeNormalizationError,
};

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// `(name, family, precision, scale, length)` of one normalized type; the integers are the
/// base-10 text of Python `int`s of any size.
type NormalizedRow = (
    String,
    &'static str,
    Option<String>,
    Option<String>,
    Option<String>,
);

/// Normalize one type: `(normalized row, Polyglot parse error)`, or Python's exception.
#[pyfunction]
#[pyo3(name = "normalize_type")]
fn normalize_type_binding(
    python: Python<'_>,
    type_sql: &str,
    dialect: &str,
) -> PyResult<(NormalizedRow, Option<String>)> {
    let normalization: Result<TypeNormalization, TypeNormalizationError> =
        compiler_guard(|| Ok(normalize_type(type_sql, dialect)))?;
    match normalization {
        Ok(TypeNormalization {
            normalized,
            parse_error,
        }) => Ok((normalized_row(normalized), parse_error)),
        Err(error) => Err(normalization_error(python, &error)),
    }
}

/// The exception the Polyglot wheel raises for the same failure.
pub(crate) fn normalization_error(python: Python<'_>, error: &TypeNormalizationError) -> PyErr {
    match error {
        TypeNormalizationError::UnknownDialect(_) => PyValueError::new_err(error.message()),
        TypeNormalizationError::Generation(_) => python
            .import("polyglot_sql")
            .and_then(|module| module.getattr("PolyglotError"))
            .and_then(|class| class.call1((error.message(),)))
            .map_or_else(|import_error| import_error, PyErr::from_value),
    }
}

fn normalized_row(normalized: NormalizedType) -> NormalizedRow {
    (
        normalized.normalized_name,
        normalized.family.as_str(),
        normalized.precision.map(|value| value.as_str().to_owned()),
        normalized.scale.map(|value| value.as_str().to_owned()),
        normalized.length.map(|value| value.as_str().to_owned()),
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(normalize_type_binding, module)?)?;
    Ok(())
}
